"""add account type and currency to accounts

Revision ID: c1a9e7f4b2d8
Revises: 9a13d2f7f3b1
Create Date: 2026-03-29 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1a9e7f4b2d8"
down_revision: Union[str, None] = "9a13d2f7f3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("account_type", sa.String(length=32), nullable=False, server_default="savings"),
    )
    op.add_column(
        "accounts",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="ARS"),
    )


def downgrade() -> None:
    op.drop_column("accounts", "currency")
    op.drop_column("accounts", "account_type")
