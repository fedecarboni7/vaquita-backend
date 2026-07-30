"""add emoji and color to categories

Revision ID: e3a7b1c2d4f5
Revises: 2b49163e2270
Create Date: 2026-07-28 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3a7b1c2d4f5"
down_revision: Union[str, None] = "2b49163e2270"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("emoji", sa.String(length=8), nullable=True))
    op.add_column("categories", sa.Column("color", sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column("categories", "color")
    op.drop_column("categories", "emoji")
