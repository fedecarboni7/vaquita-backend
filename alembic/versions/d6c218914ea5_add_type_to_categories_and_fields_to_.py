"""add_type_to_categories_and_fields_to_transactions

Revision ID: d6c218914ea5
Revises: 1484385e3813
Create Date: 2026-03-11 22:01:10.011151

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d6c218914ea5"
down_revision: Union[str, None] = "1484385e3813"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("type", sa.String(length=20), server_default="expense", nullable=False))
    op.add_column("transactions", sa.Column("installments", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("account_destination", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "account_destination")
    op.drop_column("transactions", "installments")
    op.drop_column("categories", "type")
