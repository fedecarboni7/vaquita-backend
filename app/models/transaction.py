import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.category import Category
    from app.models.subcategory import Subcategory
    from app.models.user import User


class TransactionType(str, enum.Enum):
    expense = "expense"
    income = "income"
    transfer = "transfer"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(
        back_populates="transactions",
    )
    amount: Mapped[float] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
    )
    to_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
    )
    affects_balance: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="ARS",
    )
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    receipt_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    installments: Mapped[int | None] = mapped_column(
        nullable=True,
    )
    account_destination_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expense_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
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
    category: Mapped["Category | None"] = relationship()
    subcategory: Mapped["Subcategory | None"] = relationship(back_populates="transactions")
    source_account: Mapped["Account | None"] = relationship(foreign_keys=[account_id])
    destination_account: Mapped["Account | None"] = relationship(foreign_keys=[account_destination_id])

    @property
    def account(self) -> str | None:
        if self.source_account is None:
            return None
        return self.source_account.name

    @property
    def account_destination(self) -> str | None:
        if self.destination_account is None:
            return None
        return self.destination_account.name

    @property
    def account_destination_currency(self) -> str | None:
        if self.destination_account is None:
            return None
        return self.destination_account.currency

    @property
    def category_name(self) -> str | None:
        if self.category is None:
            return None
        return self.category.name

    @property
    def subcategory_name(self) -> str | None:
        if self.subcategory is None:
            return None
        return self.subcategory.name

    __table_args__ = (Index("ix_transactions_user_id_expense_date", "user_id", "expense_date"),)
