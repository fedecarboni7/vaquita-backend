"""create budgets table

Revision ID: a7c4e1f9b2d6
Revises: e3a7b1c2d4f5
Create Date: 2026-09-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c4e1f9b2d6"
down_revision: Union[str, None] = "e3a7b1c2d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("subcategory_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subcategory_id"], ["subcategories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_budgets_user_id"), "budgets", ["user_id"], unique=False)
    op.create_index(op.f("ix_budgets_category_id"), "budgets", ["category_id"], unique=False)
    op.create_index(op.f("ix_budgets_subcategory_id"), "budgets", ["subcategory_id"], unique=False)
    op.create_index(
        "uq_budgets_user_category_currency_category_level",
        "budgets",
        ["user_id", "category_id", "currency"],
        unique=True,
        postgresql_where=sa.text("subcategory_id IS NULL"),
    )
    op.create_index(
        "uq_budgets_user_category_subcategory_currency",
        "budgets",
        ["user_id", "category_id", "subcategory_id", "currency"],
        unique=True,
        postgresql_where=sa.text("subcategory_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_budgets_user_category_subcategory_currency", table_name="budgets")
    op.drop_index("uq_budgets_user_category_currency_category_level", table_name="budgets")
    op.drop_index(op.f("ix_budgets_subcategory_id"), table_name="budgets")
    op.drop_index(op.f("ix_budgets_category_id"), table_name="budgets")
    op.drop_index(op.f("ix_budgets_user_id"), table_name="budgets")
    op.drop_table("budgets")
