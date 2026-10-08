from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, status
from groq import RateLimitError as GroqRateLimitError
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import run_agent
from app.agent.llm import get_fallback_llm
from app.auth import get_current_user
from app.config import settings
from app.database import get_session
from app.models.account import Account
from app.models.agent_usage import UsageType
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.chat import ChatMessageIn, ChatRequest, ChatResponse, PendingDraft
from app.services.ai_access import (
    INVALID_API_KEY_MESSAGE,
    ResolvedApiCredentials,
    is_llm_provider_auth_error,
    resolve_api_credentials,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@dataclass
class AgentContext:
    account_codes: dict[str, str] = field(default_factory=dict)
    account_code_to_id: dict[str, str] = field(default_factory=dict)
    account_id_to_name: dict[str, str] = field(default_factory=dict)
    account_id_to_currency: dict[str, str] = field(default_factory=dict)
    expense_category_codes: dict[str, str] = field(default_factory=dict)
    expense_category_code_to_id: dict[str, str] = field(default_factory=dict)
    expense_category_id_to_name: dict[str, str] = field(default_factory=dict)
    expense_subcategory_codes: dict[str, dict[str, str]] = field(default_factory=dict)
    expense_subcategory_code_to_id: dict[str, dict[str, str]] = field(default_factory=dict)
    expense_subcategory_id_to_name: dict[str, str] = field(default_factory=dict)
    income_category_codes: dict[str, str] = field(default_factory=dict)
    income_category_code_to_id: dict[str, str] = field(default_factory=dict)
    income_category_id_to_name: dict[str, str] = field(default_factory=dict)
    income_subcategory_codes: dict[str, dict[str, str]] = field(default_factory=dict)
    income_subcategory_code_to_id: dict[str, dict[str, str]] = field(default_factory=dict)
    income_subcategory_id_to_name: dict[str, str] = field(default_factory=dict)
    last_used_account_ids: dict[tuple[str, str], str] = field(default_factory=dict)


def _split_current_and_history(messages: list[ChatMessageIn]) -> tuple[str, list[dict] | None]:
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="messages cannot be empty",
        )

    current_message = messages[-1].content
    history = [msg.model_dump() for msg in messages[:-1]] if len(messages) > 1 else None
    return current_message, history


def _is_byok(resolved_credentials: ResolvedApiCredentials) -> bool:
    return resolved_credentials.api_key != settings.GROQ_API_KEY


def _sanitize_pending_draft(pending_draft: PendingDraft | None, ctx: AgentContext) -> dict | None:
    if pending_draft is None:
        return None

    data = pending_draft.model_dump(exclude_none=True, exclude_unset=True)
    sanitized: dict[str, object] = {}
    for key in [
        "type",
        "amount",
        "to_amount",
        "description",
        "account_id",
        "account_destination_id",
        "category_id",
        "subcategory_id",
        "expense_date",
        "currency",
        "installments",
        "note",
    ]:
        if key in data:
            sanitized[key] = data[key]

    tx_type = sanitized.get("type")
    if tx_type not in {"expense", "income", "transfer"}:
        return None

    if "account_id" in sanitized and sanitized["account_id"] not in ctx.account_id_to_name:
        sanitized.pop("account_id", None)
    if "account_destination_id" in sanitized and sanitized["account_destination_id"] not in ctx.account_id_to_name:
        sanitized.pop("account_destination_id", None)

    if tx_type == "transfer":
        sanitized.pop("category_id", None)
        sanitized.pop("subcategory_id", None)
        sanitized.pop("installments", None)
    else:
        if "category_id" in sanitized and sanitized["category_id"] not in (
            ctx.expense_category_id_to_name if tx_type == "expense" else ctx.income_category_id_to_name
        ):
            sanitized.pop("category_id", None)
        if "subcategory_id" in sanitized and sanitized["subcategory_id"] not in (
            ctx.expense_subcategory_id_to_name if tx_type == "expense" else ctx.income_subcategory_id_to_name
        ):
            sanitized.pop("subcategory_id", None)

    if "installments" in sanitized:
        installments = int(sanitized["installments"])
        if installments < 1 or installments > 60:
            sanitized.pop("installments", None)

    return sanitized or None


async def _build_chat_context(current_user: User, session: AsyncSession) -> AgentContext:
    cat_expense_result = await session.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.user_id == current_user.id, Category.type == "expense")
    )
    expense_category_rows = cat_expense_result.scalars().all()
    expense_category_codes: dict[str, str] = {}
    expense_category_code_to_id: dict[str, str] = {}
    expense_category_id_to_name: dict[str, str] = {}
    expense_subcategory_codes: dict[str, dict[str, str]] = {}
    expense_subcategory_code_to_id: dict[str, dict[str, str]] = {}
    expense_subcategory_id_to_name: dict[str, str] = {}
    for idx, category in enumerate(expense_category_rows, start=1):
        category_code = f"e{idx}"
        expense_category_codes[category.name] = category_code
        expense_category_code_to_id[category_code] = str(category.id)
        expense_category_id_to_name[str(category.id)] = category.name
        sub_categories: dict[str, str] = {}
        sub_code_map: dict[str, str] = {}
        for sub_idx, subcategory in enumerate(category.subcategories, start=1):
            sub_category_code = f"{category_code}.{sub_idx}"
            sub_categories[subcategory.name] = sub_category_code
            sub_code_map[sub_category_code] = str(subcategory.id)
            expense_subcategory_id_to_name[str(subcategory.id)] = subcategory.name
        expense_subcategory_codes[category_code] = sub_categories
        expense_subcategory_code_to_id[category_code] = sub_code_map

    cat_income_result = await session.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.user_id == current_user.id, Category.type == "income")
    )
    income_category_rows = cat_income_result.scalars().all()
    income_category_codes: dict[str, str] = {}
    income_category_code_to_id: dict[str, str] = {}
    income_category_id_to_name: dict[str, str] = {}
    income_subcategory_codes: dict[str, dict[str, str]] = {}
    income_subcategory_code_to_id: dict[str, dict[str, str]] = {}
    income_subcategory_id_to_name: dict[str, str] = {}
    for idx, category in enumerate(income_category_rows, start=1):
        category_code = f"i{idx}"
        income_category_codes[category.name] = category_code
        income_category_code_to_id[category_code] = str(category.id)
        income_category_id_to_name[str(category.id)] = category.name
        sub_categories: dict[str, str] = {}
        sub_code_map: dict[str, str] = {}
        for sub_idx, subcategory in enumerate(category.subcategories, start=1):
            sub_category_code = f"{category_code}.{sub_idx}"
            sub_categories[subcategory.name] = sub_category_code
            sub_code_map[sub_category_code] = str(subcategory.id)
            income_subcategory_id_to_name[str(subcategory.id)] = subcategory.name
        income_subcategory_codes[category_code] = sub_categories
        income_subcategory_code_to_id[category_code] = sub_code_map

    acc_result = await session.execute(
        select(Account.id, Account.name, Account.currency)
        .where(Account.user_id == current_user.id)
        .order_by(Account.created_at.asc(), Account.id.asc())
    )
    account_rows = acc_result.all()
    account_codes: dict[str, str] = {}
    account_code_to_id: dict[str, str] = {}
    account_id_to_name: dict[str, str] = {}
    account_id_to_currency: dict[str, str] = {}
    for idx, (account_id, account_name, currency) in enumerate(account_rows, start=1):
        code = f"a{idx}"
        account_codes[account_name] = code
        account_code_to_id[code] = str(account_id)
        account_id_to_name[str(account_id)] = account_name
        account_id_to_currency[str(account_id)] = currency

    last_used_result = await session.execute(
        select(Transaction.type, Account.currency, Account.id)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.type.in_([TransactionType.expense, TransactionType.income]),
        )
        .order_by(Transaction.created_at.desc())
        .limit(50)
    )
    last_used_account_ids: dict[tuple[str, str], str] = {}
    seen: set[tuple[str, str]] = set()
    for tx_type, currency, account_id in last_used_result:
        key = (tx_type.value, currency or "ARS")
        if key in seen:
            continue
        last_used_account_ids[key] = str(account_id)
        seen.add(key)

    return AgentContext(
        account_codes=account_codes,
        account_code_to_id=account_code_to_id,
        account_id_to_name=account_id_to_name,
        account_id_to_currency=account_id_to_currency,
        expense_category_codes=expense_category_codes,
        expense_category_code_to_id=expense_category_code_to_id,
        expense_category_id_to_name=expense_category_id_to_name,
        expense_subcategory_codes=expense_subcategory_codes,
        expense_subcategory_code_to_id=expense_subcategory_code_to_id,
        expense_subcategory_id_to_name=expense_subcategory_id_to_name,
        income_category_codes=income_category_codes,
        income_category_code_to_id=income_category_code_to_id,
        income_category_id_to_name=income_category_id_to_name,
        income_subcategory_codes=income_subcategory_codes,
        income_subcategory_code_to_id=income_subcategory_code_to_id,
        income_subcategory_id_to_name=income_subcategory_id_to_name,
        last_used_account_ids=last_used_account_ids,
    )


async def _process_chat_message(
    *,
    current_message: str,
    provider: str,
    api_key: str,
    history: list[dict] | None,
    current_user: User,
    session: AsyncSession,
    is_byok: bool,
    pending_draft: PendingDraft | None,
) -> dict:
    context = await _build_chat_context(current_user=current_user, session=session)
    try:
        return await run_agent(
            message=current_message,
            provider=provider,
            api_key=api_key,
            history=history,
            pending_draft=_sanitize_pending_draft(pending_draft, context),
            agent_context=context,
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
                pending_draft=_sanitize_pending_draft(pending_draft, context),
                agent_context=context,
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
                    pending_draft=_sanitize_pending_draft(pending_draft, context),
                    agent_context=context,
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
) -> ChatResponse:
    return ChatResponse(
        response_type=result["response_type"],
        message=result["message"],
        data=result.get("data"),
        transcribed_text=transcribed_text,
        fallback_model_used=result.get("fallback_used", False),
    )


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Run the user message through the AI agent."""
    current_message, history = _split_current_and_history(body.messages)
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
            pending_draft=body.pending_draft,
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

    return _build_chat_response(result)
