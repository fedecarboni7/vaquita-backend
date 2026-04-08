"""add account include_in_total and fixed billing period dates

Revision ID: f4a1b9c2d3e4
Revises: b1f8f0c2a9d1
Create Date: 2026-04-08 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4a1b9c2d3e4"
down_revision: str | Sequence[str] | None = "b1f8f0c2a9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("include_in_total", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("accounts", sa.Column("billing_period_start", sa.Date(), nullable=True))
    op.add_column("accounts", sa.Column("billing_period_end", sa.Date(), nullable=True))
    op.add_column("accounts", sa.Column("payment_due_date", sa.Date(), nullable=True))

    op.execute(sa.text("UPDATE accounts SET include_in_total = FALSE WHERE account_type = 'credit_card'"))


def downgrade() -> None:
    op.drop_column("accounts", "payment_due_date")
    op.drop_column("accounts", "billing_period_end")
    op.drop_column("accounts", "billing_period_start")
    op.drop_column("accounts", "include_in_total")
