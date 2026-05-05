import uuid
import datetime

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UploadUsage(Base):
    __tablename__ = "upload_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    upload_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    upload_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "upload_date", name="uq_upload_usage_user_date"),
    )
