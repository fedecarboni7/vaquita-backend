"""add ondelete cascade to user foreign keys

Revision ID: 5fce840eb9de
Revises: f2c3d4e5a6b7
Create Date: 2026-04-28 14:45:07.483925

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5fce840eb9de"
down_revision: Union[str, None] = "f2c3d4e5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("accounts_user_id_fkey", "accounts", type_="foreignkey")
    op.create_foreign_key("accounts_user_id_fkey", "accounts", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("categories_user_id_fkey", "categories", type_="foreignkey")
    op.create_foreign_key("categories_user_id_fkey", "categories", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("transactions_user_id_fkey", "transactions", type_="foreignkey")
    op.create_foreign_key("transactions_user_id_fkey", "transactions", "users", ["user_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("transactions_user_id_fkey", "transactions", type_="foreignkey")
    op.create_foreign_key("transactions_user_id_fkey", "transactions", "users", ["user_id"], ["id"])
    op.drop_constraint("categories_user_id_fkey", "categories", type_="foreignkey")
    op.create_foreign_key("categories_user_id_fkey", "categories", "users", ["user_id"], ["id"])
    op.drop_constraint("accounts_user_id_fkey", "accounts", type_="foreignkey")
    op.create_foreign_key("accounts_user_id_fkey", "accounts", "users", ["user_id"], ["id"])
