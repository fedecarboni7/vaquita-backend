import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.user import User
from app.models.user_api_key import UserApiKey
from app.schemas.settings import ApiKeyStatusResponse, ApiKeyUpsertRequest
from app.services.encryption import encrypt_key

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/api-key", response_model=ApiKeyStatusResponse)
async def get_api_key_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyStatusResponse:
    result = await session.execute(select(UserApiKey).where(UserApiKey.user_id == current_user.id))
    user_api_key = result.scalar_one_or_none()

    if user_api_key is None:
        return ApiKeyStatusResponse(has_key=False)

    return ApiKeyStatusResponse(
        provider=user_api_key.provider,
        has_key=True,
    )


@router.post("/api-key", response_model=ApiKeyStatusResponse)
async def save_api_key(
    body: ApiKeyUpsertRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyStatusResponse:
    result = await session.execute(select(UserApiKey).where(UserApiKey.user_id == current_user.id))
    existing = result.scalar_one_or_none()

    encrypted_key = encrypt_key(body.api_key)
    if existing is None:
        existing = UserApiKey(
            id=uuid.uuid4(),
            user_id=current_user.id,
            provider=body.provider,
            encrypted_key=encrypted_key,
        )
        session.add(existing)
    else:
        existing.provider = body.provider
        existing.encrypted_key = encrypted_key

    await session.commit()

    return ApiKeyStatusResponse(provider=existing.provider, has_key=True)


@router.delete("/api-key", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(select(UserApiKey).where(UserApiKey.user_id == current_user.id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)
        await session.commit()
