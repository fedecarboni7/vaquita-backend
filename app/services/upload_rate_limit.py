import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.upload_usage import UploadUsage


async def check_and_increment_upload_usage(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Verify the user hasn't exceeded the daily receipt upload limit.

    Increments the counter atomically using an upsert.
    Raises HTTPException 429 if the limit is exceeded.
    """
    today = date.today()
    daily_limit = settings.RECEIPT_DAILY_LIMIT

    stmt = (
        insert(UploadUsage)
        .values(user_id=user_id, upload_date=today, upload_count=1)
        .on_conflict_do_update(
            index_elements=["user_id", "upload_date"],
            set_={"upload_count": UploadUsage.upload_count + 1},
        )
        .returning(UploadUsage.upload_count)
    )

    result = await session.execute(stmt)
    current_count = result.scalar_one()

    if current_count > daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Límite diario de comprobantes alcanzado. Podés cargar hasta {daily_limit} por día.",
        )
