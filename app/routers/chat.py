import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from groq import RateLimitError as GroqRateLimitError
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import run_agent
from app.agent.llm import get_fallback_llm
from app.auth import get_current_user
from app.config import settings
from app.database import get_session
from app.models.agent_usage import UsageType
from app.models.account import Account
from app.models.category import Category
from app.models.chat_interaction import ChatInteraction
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.chat import (
    ChatMessageIn,
    ChatRequest,
    ChatResponse,
    ChatThreadDetailResponse,
    ChatThreadInteraction,
    ChatThreadSummary,
    ChatThreadsResponse,
)
from app.services.ai_access import (
    INVALID_API_KEY_MESSAGE,
    ResolvedApiCredentials,
    is_llm_provider_auth_error,
    resolve_api_credentials,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _split_current_and_history(messages: list[ChatMessageIn]) -> tuple[str, list[dict] | None]:
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid messages payload",
        ) from exc

    if not isinstance(raw_messages, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid messages payload",
        )

    try:
        parsed_messages = [ChatMessageIn.model_validate(item) for item in raw_messages]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid messages payload",
        ) from exc

    return [msg.model_dump() for msg in parsed_messages] if parsed_messages else None


def _is_byok(resolved_credentials: ResolvedApiCredentials) -> bool:
    return resolved_credentials.api_key != settings.GROQ_API_KEY


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

    acc_result = await session.execute(
        select(Account.id, Account.name)
        .where(Account.user_id == current_user.id)
        .order_by(Account.created_at.asc(), Account.id.asc())
    )
    account_rows = acc_result.all()
    accounts: list[str] = []
    account_name_to_id: dict[str, str] = {}
    for account_id, account_name in account_rows:
        normalized_name = account_name.strip().lower()
        if normalized_name in account_name_to_id:
            continue
        accounts.append(account_name)
        account_name_to_id[normalized_name] = str(account_id)

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
        "account_name_to_id": account_name_to_id,
    }


async def _process_chat_message(
    *,
    current_message: str,
    provider: str,
    api_key: str,
    history: list[dict] | None,
    current_user: User,
    session: AsyncSession,
    is_byok: bool,
) -> dict:
    context = await _build_chat_context(current_user=current_user, session=session)
    try:
        return await run_agent(
            message=current_message,
            provider=provider,
            api_key=api_key,
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
            account_name_to_id=context["account_name_to_id"],
        )
    except GroqRateLimitError:
        if not is_byok:
            return {
                "response_type": "answer",
                "message": (
                    "Alcanzaste el límite diario de tokens de tu API key de Groq. "
                    "Podés volver a intentarlo mañana o cambiar de proveedor en Configuración."
                ),
                "data": None,
            }
        fallback_llm = get_fallback_llm(provider=provider, api_key=api_key)
        if fallback_llm is None:
            return {
                "response_type": "answer",
                "message": (
                    "Alcanzaste el límite diario de tokens de tu API key de Groq. "
                    "Podés volver a intentarlo mañana o cambiar de proveedor en Configuración."
                ),
                "data": None,
            }
        try:
            result = await run_agent(
                message=current_message,
                provider=provider,
                api_key=api_key,
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
                account_name_to_id=context["account_name_to_id"],
                llm_override=fallback_llm,
            )
            result["fallback_used"] = True
            return result
        except GroqRateLimitError:
            return {
                "response_type": "answer",
                "message": (
                    "Alcanzaste el límite de tu modelo principal y del modelo de respaldo. Intentá de nuevo más tarde."
                ),
                "data": None,
            }
    except ChatGoogleGenerativeAIError as exc:
        if "429" in str(exc):
            if not is_byok:
                return {
                    "response_type": "answer",
                    "message": (
                        "Alcanzaste el límite diario de tu API key de Google AI Studio. "
                        "Podés volver a intentarlo mañana o cambiar de proveedor en Configuración."
                    ),
                    "data": None,
                }
            fallback_llm = get_fallback_llm(provider=provider, api_key=api_key)
            if fallback_llm is None:
                return {
                    "response_type": "answer",
                    "message": (
                        "Alcanzaste el límite diario de tu API key de Google AI Studio. "
                        "Podés volver a intentarlo mañana o cambiar de proveedor en Configuración."
                    ),
                    "data": None,
                }
            try:
                result = await run_agent(
                    message=current_message,
                    provider=provider,
                    api_key=api_key,
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
                    account_name_to_id=context["account_name_to_id"],
                    llm_override=fallback_llm,
                )
                result["fallback_used"] = True
                return result
            except ChatGoogleGenerativeAIError as fallback_exc:
                if "429" in str(fallback_exc):
                    return {
                        "response_type": "answer",
                        "message": (
                            "Alcanzaste el límite de tu modelo principal y del modelo de respaldo. "
                            "Intentá de nuevo más tarde."
                        ),
                        "data": None,
                    }
                raise
        raise


def _build_chat_response(
    result: dict,
    *,
    transcribed_text: str | None = None,
    thread_id: uuid.UUID | None = None,
) -> ChatResponse:
    return ChatResponse(
        response_type=result["response_type"],
        message=result["message"],
        data=result.get("data"),
        transcribed_text=transcribed_text,
        fallback_model_used=result.get("fallback_used", False),
        thread_id=thread_id,
    )


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Run the user message through the AI agent."""
    current_message, history = _split_current_and_history(body.messages)
    resolved_thread_id = body.thread_id or uuid.uuid4()
    resolved_credentials = await resolve_api_credentials(
        current_user=current_user,
        session=session,
        usage_type=UsageType.chat,
    )
    try:
        result = await _process_chat_message(
            current_message=current_message,
            provider=resolved_credentials.provider,
            api_key=resolved_credentials.api_key,
            history=history,
            current_user=current_user,
            session=session,
            is_byok=_is_byok(resolved_credentials),
        )
    except HTTPException:
        raise
    except Exception as exc:
        if is_llm_provider_auth_error(exc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=INVALID_API_KEY_MESSAGE,
            ) from exc
        raise

    session.add(
        ChatInteraction(
            user_id=current_user.id,
            thread_id=resolved_thread_id,
            user_message=current_message,
            agent_reply=result["message"],
        )
    )
    await session.commit()

    return _build_chat_response(result, thread_id=resolved_thread_id)


@router.get("/threads", response_model=ChatThreadsResponse)
async def list_chat_threads(
    q: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatThreadsResponse:
    base_query = select(
        ChatInteraction.thread_id.label("thread_id"),
        func.min(ChatInteraction.created_at).label("started_at"),
        func.count(ChatInteraction.id).label("interaction_count"),
    ).where(ChatInteraction.user_id == current_user.id)

    if q and q.strip():
        search_term = f"%{q.strip()}%"
        base_query = base_query.where(
            or_(
                ChatInteraction.user_message.ilike(search_term),
                ChatInteraction.agent_reply.ilike(search_term),
            )
        )

    thread_subquery = base_query.group_by(ChatInteraction.thread_id).subquery()
    transactions_count = (
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == current_user.id,
            Transaction.chat_thread_id == thread_subquery.c.thread_id,
        )
        .scalar_subquery()
    )

    query = select(
        thread_subquery.c.thread_id,
        thread_subquery.c.started_at,
        thread_subquery.c.interaction_count,
        transactions_count.label("transactions_created"),
    ).order_by(thread_subquery.c.started_at.desc())

    result = await session.execute(query)
    threads = [
        ChatThreadSummary(
            thread_id=row.thread_id,
            started_at=row.started_at,
            interaction_count=row.interaction_count,
            transactions_created=row.transactions_created or 0,
        )
        for row in result.all()
    ]
    return ChatThreadsResponse(threads=threads)


@router.get("/threads/{thread_id}", response_model=ChatThreadDetailResponse)
async def get_chat_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatThreadDetailResponse:
    exists_result = await session.execute(
        select(ChatInteraction.id)
        .where(
            ChatInteraction.user_id == current_user.id,
            ChatInteraction.thread_id == thread_id,
        )
        .limit(1)
    )
    if exists_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversacion no encontrada",
        )

    interactions_result = await session.execute(
        select(ChatInteraction)
        .where(
            ChatInteraction.user_id == current_user.id,
            ChatInteraction.thread_id == thread_id,
        )
        .order_by(ChatInteraction.created_at.asc())
    )

    interactions = [
        ChatThreadInteraction(
            id=interaction.id,
            user_message=interaction.user_message,
            agent_reply=interaction.agent_reply,
            created_at=interaction.created_at,
        )
        for interaction in interactions_result.scalars().all()
    ]
    return ChatThreadDetailResponse(thread_id=thread_id, interactions=interactions)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    exists_result = await session.execute(
        select(ChatInteraction.id)
        .where(
            ChatInteraction.user_id == current_user.id,
            ChatInteraction.thread_id == thread_id,
        )
        .limit(1)
    )
    if exists_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversacion no encontrada",
        )

    await session.execute(
        delete(ChatInteraction).where(
            ChatInteraction.user_id == current_user.id,
            ChatInteraction.thread_id == thread_id,
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
