import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.subcategory import Subcategory
    from app.models.user import User


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        Index(
            "uq_budgets_user_category_currency_category_level",
            "user_id",
            "category_id",
            "currency",
            unique=True,
            postgresql_where=text("subcategory_id IS NULL"),
        ),
        Index(
            "uq_budgets_user_category_subcategory_currency",
            "user_id",
            "category_id",
            "subcategory_id",
            "currency",
            unique=True,
            postgresql_where=text("subcategory_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=14, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ARS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()
    category: Mapped["Category"] = relationship()
    subcategory: Mapped["Subcategory | None"] = relationship()
