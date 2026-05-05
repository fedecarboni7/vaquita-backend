"""add_upload_usage_table

Revision ID: ef4ac4e80443
Revises: c9f1e2d3b4a5
Create Date: 2026-05-04 20:21:50.913648

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef4ac4e80443'
down_revision: Union[str, None] = 'c9f1e2d3b4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upload_usage",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upload_date", sa.Date(), nullable=False),
        sa.Column("upload_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("user_id", "upload_date", name="uq_upload_usage_user_date"),
    )


def downgrade() -> None:
    op.drop_table("upload_usage")
