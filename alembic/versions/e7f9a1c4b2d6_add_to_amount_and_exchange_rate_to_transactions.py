"""add to_amount and exchange_rate to transactions

Revision ID: e7f9a1c4b2d6
Revises: 7c2e9d6a1b45
Create Date: 2026-04-16 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7f9a1c4b2d6"
down_revision: str | Sequence[str] | None = "7c2e9d6a1b45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("to_amount", sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column("transactions", sa.Column("exchange_rate", sa.Numeric(precision=15, scale=6), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "exchange_rate")
    op.drop_column("transactions", "to_amount")
