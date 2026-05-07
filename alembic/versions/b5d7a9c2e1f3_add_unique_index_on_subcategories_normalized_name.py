"""add unique index on subcategories normalized name

Revision ID: b5d7a9c2e1f3
Revises: a3c9b1d4e2f0
Create Date: 2026-05-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b5d7a9c2e1f3"
down_revision: Union[str, None] = "a3c9b1d4e2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_subcategories_user_category_normalized_name",
        "subcategories",
        [sa.text("user_id"), sa.text("category_id"), sa.text("lower(btrim(name))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_subcategories_user_category_normalized_name", table_name="subcategories")
