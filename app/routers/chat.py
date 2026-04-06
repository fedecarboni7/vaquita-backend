import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import run_agent
from app.auth import get_current_user
from app.database import get_session
from app.models.account import Account
from app.models.category import Category
from app.models.user import User
from app.schemas.chat import ChatMessageIn, ChatRequest, ChatResponse
from app.services.transcription import transcribe_audio_bytes

router = APIRouter(prefix="/chat", tags=["chat"])
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _split_current_and_history(messages: list[ChatMessageIn]) -> tuple[str, list[dict] | None]:
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="messages cannot be empty",
        )

    current_message = messages[-1].content
    history = [msg.model_dump() for msg in messages[:-1]] if len(messages) > 1 else None
    return current_message, history


def _parse_messages_form(messages: str | None) -> list[dict] | None:
    if not messages:
        return None

    try:
        raw_messages = json.loads(messages)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid messages payload",
        ) from exc

    if not isinstance(raw_messages, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid messages payload",
        )

    try:
        parsed_messages = [ChatMessageIn.model_validate(item) for item in raw_messages]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid messages payload",
        ) from exc

    return [msg.model_dump() for msg in parsed_messages] if parsed_messages else None


async def _build_chat_context(current_user: User, session: AsyncSession) -> dict:
    cat_expense_result = await session.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.user_id == current_user.id, Category.type == "expense")
    )
    expense_category_rows = cat_expense_result.scalars().all()
    expense_categories = [category.name for category in expense_category_rows]
    expense_category_tree: list[dict] = []
    expense_category_index: dict[str, str] = {}
    expense_subcategory_index: dict[str, dict[str, str]] = {}
    for category in expense_category_rows:
        subcategories = [subcategory.name for subcategory in category.subcategories]
        expense_category_tree.append({"category": category.name, "subcategories": subcategories})
        expense_category_index[category.name] = str(category.id)
        expense_subcategory_index[category.name] = {
            subcategory.name: str(subcategory.id) for subcategory in category.subcategories
        }

    cat_income_result = await session.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.user_id == current_user.id, Category.type == "income")
    )
    income_category_rows = cat_income_result.scalars().all()
    income_categories = [category.name for category in income_category_rows]
    income_category_tree: list[dict] = []
    income_category_index: dict[str, str] = {}
    income_subcategory_index: dict[str, dict[str, str]] = {}
    for category in income_category_rows:
        subcategories = [subcategory.name for subcategory in category.subcategories]
        income_category_tree.append({"category": category.name, "subcategories": subcategories})
        income_category_index[category.name] = str(category.id)
        income_subcategory_index[category.name] = {
            subcategory.name: str(subcategory.id) for subcategory in category.subcategories
        }

    acc_result = await session.execute(select(Account.name).where(Account.user_id == current_user.id))
    accounts = [row[0] for row in acc_result.all()]

    return {
        "expense_categories": expense_categories,
        "income_categories": income_categories,
        "expense_category_tree": expense_category_tree,
        "income_category_tree": income_category_tree,
        "expense_category_index": expense_category_index,
        "income_category_index": income_category_index,
        "expense_subcategory_index": expense_subcategory_index,
        "income_subcategory_index": income_subcategory_index,
        "accounts": accounts,
    }


async def _process_chat_message(
    *,
    current_message: str,
    history: list[dict] | None,
    current_user: User,
    session: AsyncSession,
) -> dict:
    context = await _build_chat_context(current_user=current_user, session=session)
    return await run_agent(
        message=current_message,
        history=history,
        expense_categories=context["expense_categories"],
        income_categories=context["income_categories"],
        expense_category_tree=context["expense_category_tree"],
        income_category_tree=context["income_category_tree"],
        expense_category_index=context["expense_category_index"],
        income_category_index=context["income_category_index"],
        expense_subcategory_index=context["expense_subcategory_index"],
        income_subcategory_index=context["income_subcategory_index"],
        accounts=context["accounts"],
    )


def _build_chat_response(result: dict, transcribed_text: str | None = None) -> ChatResponse:
    return ChatResponse(
        response_type=result["response_type"],
        message=result["message"],
        data=result.get("data"),
        transcribed_text=transcribed_text,
    )


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Run the user message through the AI agent."""
    current_message, history = _split_current_and_history(body.messages)
    result = await _process_chat_message(
        current_message=current_message,
        history=history,
        current_user=current_user,
        session=session,
    )
    return _build_chat_response(result)


@router.post("/audio", response_model=ChatResponse)
async def chat_audio(
    audio: UploadFile = File(...),
    messages: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Transcribe audio with Gemini and run the same chat agent flow."""
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser de audio",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El audio enviado esta vacio",
        )

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El audio excede el tamano maximo permitido",
        )

    history = _parse_messages_form(messages)

    try:
        transcribed_text = await transcribe_audio_bytes(
            audio_bytes=audio_bytes,
            mime_type=audio.content_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo transcribir el audio",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La transcripción de audio no esta configurada",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al transcribir el audio",
        ) from exc

    result = await _process_chat_message(
        current_message=transcribed_text,
        history=history,
        current_user=current_user,
        session=session,
    )
    return _build_chat_response(result, transcribed_text=transcribed_text)
