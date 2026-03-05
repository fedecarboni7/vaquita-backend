from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, verify_google_token
from app.database import get_session
from app.models.user import User
from app.schemas.auth import GoogleAuthRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=TokenResponse)
async def google_auth(
    body: GoogleAuthRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify a Google credential and return a JWT access token.

    If the user doesn't exist, creates a new account.
    If it does exist, updates email and display_name from Google.
    """
    google_payload = await verify_google_token(body.credential)

    google_id = google_payload["sub"]
    email = google_payload.get("email", "")
    display_name = google_payload.get("name")

    result = await session.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            google_id=google_id,
        )
        session.add(user)
    else:
        user.email = email
        user.display_name = display_name

    await session.commit()
    await session.refresh(user)

    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user
