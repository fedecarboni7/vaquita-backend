import uuid
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models.user import User

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/google")

_google_jwks: dict | None = None


async def _get_google_jwks() -> dict:
    """Fetch and cache Google's public JWKS keys."""
    global _google_jwks
    if _google_jwks is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(GOOGLE_JWKS_URL)
            resp.raise_for_status()
            _google_jwks = resp.json()
    return _google_jwks


async def verify_google_token(credential: str) -> dict:
    """Verify a Google ID token and return its payload.

    Decodes the JWT using Google's public keys, validating the
    issuer, audience, and expiration.
    """
    jwks = await _get_google_jwks()
    try:
        payload = jwt.decode(
            credential,
            jwks,
            algorithms=["RS256"],
            audience=settings.GOOGLE_CLIENT_ID,
            issuer=GOOGLE_ISSUERS,
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google credential: {e}",
        ) from e

    return payload


def create_access_token(user_id: uuid.UUID) -> str:
    """Create a JWT access token for the given user ID."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """FastAPI dependency that extracts and validates the current user from the JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError) as e:
        raise credentials_exception from e

    user = await session.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user
