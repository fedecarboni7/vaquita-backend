from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_usage import AgentUsage, UsageType
from app.models.user import User
from app.models.user_api_key import UserApiKey
from app.schemas.chat import SessionApiKeyPayload
from app.services.encryption import decrypt_key

FREE_LIMIT_REACHED_MESSAGE = (
    "Alcanzaste el límite diario gratuito. Agregá tu propia API key en Configuración para seguir usando el agente."
)
FALLBACK_API_KEY_MISSING_MESSAGE = "No hay API key de fallback configurada en el servidor."
INVALID_API_KEY_MESSAGE = "Tu API key no es válida. Revisá que sea correcta en Configuración."


@dataclass(slots=True)
class ResolvedApiCredentials:
    provider: str
    api_key: str


async def _get_persisted_user_api_key(
    *,
    current_user: User,
    session: AsyncSession,
) -> tuple[str, str] | None:
    result = await session.execute(select(UserApiKey).where(UserApiKey.user_id == current_user.id))
    user_api_key = result.scalar_one_or_none()
    if user_api_key is None or not user_api_key.persist:
        return None

    return user_api_key.provider.value, decrypt_key(user_api_key.encrypted_key)


async def _consume_free_quota(
    *,
    current_user: User,
    session: AsyncSession,
    usage_type: UsageType,
) -> bool:
    today = date.today()
    usage = await session.get(
        AgentUsage,
        {
            "user_id": current_user.id,
            "date": today,
            "usage_type": usage_type,
        },
    )

    if usage is None:
        usage = AgentUsage(
            user_id=current_user.id,
            date=today,
            usage_type=usage_type,
            request_count=1,
        )
        session.add(usage)
        await session.commit()
        return True

    if usage.request_count >= settings.FREE_DAILY_LIMIT:
        return False

    usage.request_count += 1
    await session.commit()
    return True


async def resolve_api_credentials(
    *,
    current_user: User,
    session: AsyncSession,
    usage_type: UsageType,
    session_api_key: SessionApiKeyPayload | None = None,
) -> ResolvedApiCredentials:
    if session_api_key is not None:
        return ResolvedApiCredentials(
            provider=session_api_key.provider.value,
            api_key=session_api_key.api_key,
        )

    persisted_credentials = await _get_persisted_user_api_key(current_user=current_user, session=session)
    if persisted_credentials is not None:
        provider, api_key = persisted_credentials
        return ResolvedApiCredentials(provider=provider, api_key=api_key)

    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=FALLBACK_API_KEY_MISSING_MESSAGE,
        )

    within_limit = await _consume_free_quota(
        current_user=current_user,
        session=session,
        usage_type=usage_type,
    )
    if not within_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=FREE_LIMIT_REACHED_MESSAGE,
        )

    return ResolvedApiCredentials(provider="groq", api_key=settings.GROQ_API_KEY)


def is_llm_provider_auth_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in {400, 401, 403}:
        return True

    if isinstance(error, ValueError) and "unsupported provider" in str(error).lower():
        return True

    text = str(error).lower()
    auth_markers = (
        "invalid api key",
        "api key is invalid",
        "incorrect api key",
        "authentication",
        "unauthorized",
        "forbidden",
        "permission denied",
        "permissiondenied",
        "unauthenticated",
        "credentials",
        "invalid_argument",
    )
    return any(marker in text for marker in auth_markers)
