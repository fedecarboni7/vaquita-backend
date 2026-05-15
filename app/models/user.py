import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent_usage import AgentUsage
    from app.models.account import Account
    from app.models.category import Category
    from app.models.chat_interaction import ChatInteraction
    from app.models.subcategory import Subcategory
    from app.models.transaction import Transaction
    from app.models.user_api_key import UserApiKey


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    google_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user",
    )
    accounts: Mapped[list["Account"]] = relationship(
        back_populates="user",
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="user",
    )
    subcategories: Mapped[list["Subcategory"]] = relationship(
        back_populates="user",
    )
    api_key: Mapped["UserApiKey | None"] = relationship(
        back_populates="user",
        uselist=False,
    )
    agent_usage_entries: Mapped[list["AgentUsage"]] = relationship(
        back_populates="user",
    )
    chat_interactions: Mapped[list["ChatInteraction"]] = relationship(
        back_populates="user",
    )
