"""add unique index on categories normalized name

Revision ID: a3c9b1d4e2f0
Revises: ef4ac4e80443
Create Date: 2026-05-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3c9b1d4e2f0"
down_revision: Union[str, None] = "ef4ac4e80443"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_categories_user_type_normalized_name",
        "categories",
        [sa.text("user_id"), sa.text("type"), sa.text("lower(btrim(name))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_categories_user_type_normalized_name", table_name="categories")
