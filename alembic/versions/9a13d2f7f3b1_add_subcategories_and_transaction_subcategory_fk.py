"""add subcategories and transaction subcategory fk

Revision ID: 9a13d2f7f3b1
Revises: d6c218914ea5
Create Date: 2026-03-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a13d2f7f3b1"
down_revision: Union[str, None] = "d6c218914ea5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subcategories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category_id", "name", name="uq_subcategories_user_category_name"),
    )
    op.create_index(op.f("ix_subcategories_category_id"), "subcategories", ["category_id"], unique=False)
    op.create_index(op.f("ix_subcategories_user_id"), "subcategories", ["user_id"], unique=False)

    op.add_column("transactions", sa.Column("subcategory_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_transactions_subcategory_id_subcategories",
        "transactions",
        "subcategories",
        ["subcategory_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_transactions_subcategory_id"), "transactions", ["subcategory_id"], unique=False)

    op.drop_column("transactions", "subcategory")


def downgrade() -> None:
    op.add_column("transactions", sa.Column("subcategory", sa.String(length=100), nullable=True))
    op.drop_index(op.f("ix_transactions_subcategory_id"), table_name="transactions")
    op.drop_constraint("fk_transactions_subcategory_id_subcategories", "transactions", type_="foreignkey")
    op.drop_column("transactions", "subcategory_id")

    op.drop_index(op.f("ix_subcategories_user_id"), table_name="subcategories")
    op.drop_index(op.f("ix_subcategories_category_id"), table_name="subcategories")
    op.drop_table("subcategories")
