"""drop exchange_rate from transactions

Revision ID: b7c4d2e9a6f1
Revises: e7f9a1c4b2d6
Create Date: 2026-04-16 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c4d2e9a6f1"
down_revision: str | Sequence[str] | None = "e7f9a1c4b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("transactions", "exchange_rate")


def downgrade() -> None:
    op.add_column("transactions", sa.Column("exchange_rate", sa.Numeric(precision=15, scale=6), nullable=True))
