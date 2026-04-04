"""make transaction account and description nullable

Revision ID: b1f8f0c2a9d1
Revises: 45022d06d57c
Create Date: 2026-04-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1f8f0c2a9d1"
down_revision: str | Sequence[str] | None = "45022d06d57c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("transactions", "account", existing_type=sa.String(length=100), nullable=True)
    op.alter_column("transactions", "description", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE transactions SET account = '' WHERE account IS NULL")
    op.execute("UPDATE transactions SET description = '' WHERE description IS NULL")
    op.alter_column("transactions", "account", existing_type=sa.String(length=100), nullable=False)
    op.alter_column("transactions", "description", existing_type=sa.String(length=255), nullable=False)
