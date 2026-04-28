from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    await db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": current_user.id})
    await db.commit()
