"""add receipt url to transactions

Revision ID: c9f1e2d3b4a5
Revises: 5fce840eb9de
Create Date: 2026-05-04 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9f1e2d3b4a5"
down_revision: str | Sequence[str] | None = "5fce840eb9de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("receipt_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "receipt_url")
