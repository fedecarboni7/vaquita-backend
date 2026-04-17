"""add affects_balance to transactions

Revision ID: d2f7a8c9b1e0
Revises: b7c4d2e9a6f1
Create Date: 2026-04-17 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2f7a8c9b1e0"
down_revision: str | Sequence[str] | None = "b7c4d2e9a6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("affects_balance", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("transactions", "affects_balance")
