"""add user api keys and agent usage tables

Revision ID: b4b49cfe10bf
Revises: d2f7a8c9b1e0
Create Date: 2026-04-24 16:19:50.527668

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4b49cfe10bf"
down_revision: Union[str, None] = "d2f7a8c9b1e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    provider_enum = sa.Enum("groq", "google", name="llm_provider")

    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", provider_enum, nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("persist", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_api_keys_user_id"),
    )
    op.create_index(op.f("ix_user_api_keys_user_id"), "user_api_keys", ["user_id"], unique=False)

    op.create_table(
        "agent_usage",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "date", name="pk_agent_usage_user_date"),
    )
    op.create_index(op.f("ix_agent_usage_user_id"), "agent_usage", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_usage_user_id"), table_name="agent_usage")
    op.drop_table("agent_usage")

    op.drop_index(op.f("ix_user_api_keys_user_id"), table_name="user_api_keys")
    op.drop_table("user_api_keys")

    provider_enum = sa.Enum("groq", "google", name="llm_provider")
    provider_enum.drop(op.get_bind(), checkfirst=True)
