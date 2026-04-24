import uuid
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class AgentUsage(Base):
    __tablename__ = "agent_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    request_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    user: Mapped["User"] = relationship(back_populates="agent_usage_entries")
