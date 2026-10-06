import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_token import AuthToken

EMAIL_VERIFICATION_PURPOSE = "email_verification"
PASSWORD_RESET_PURPOSE = "password_reset"
TOKEN_LIFETIMES = {
    EMAIL_VERIFICATION_PURPOSE: timedelta(hours=24),
    PASSWORD_RESET_PURPOSE: timedelta(hours=1),
}


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def issue_token(session: AsyncSession, user_id: uuid.UUID, purpose: str) -> str:
    lifetime = TOKEN_LIFETIMES[purpose]
    now = datetime.now(timezone.utc)
    await session.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = secrets.token_urlsafe(32)
    session.add(
        AuthToken(
            user_id=user_id,
            token_hash=hash_token(raw_token),
            purpose=purpose,
            expires_at=now + lifetime,
        )
    )
    await session.flush()
    return raw_token


async def consume_token(session: AsyncSession, raw_token: str, purpose: str) -> AuthToken | None:
    result = await session.execute(
        select(AuthToken)
        .where(AuthToken.token_hash == hash_token(raw_token), AuthToken.purpose == purpose)
        .with_for_update()
    )
    token = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if token is None or token.used_at is not None or token.expires_at <= now:
        return None
    token.used_at = now
    return token
