"""add chat interactions and thread id

Revision ID: c2d4a1b9e8f0
Revises: 04557a304a38
Create Date: 2026-05-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d4a1b9e8f0"
down_revision: Union[str, None] = "04557a304a38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_interactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("agent_reply", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_interactions_thread_id"), "chat_interactions", ["thread_id"], unique=False)
    op.create_index(op.f("ix_chat_interactions_user_id"), "chat_interactions", ["user_id"], unique=False)

    op.add_column("transactions", sa.Column("chat_thread_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_transactions_chat_thread_id"), "transactions", ["chat_thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_chat_thread_id"), table_name="transactions")
    op.drop_column("transactions", "chat_thread_id")

    op.drop_index(op.f("ix_chat_interactions_user_id"), table_name="chat_interactions")
    op.drop_index(op.f("ix_chat_interactions_thread_id"), table_name="chat_interactions")
    op.drop_table("chat_interactions")
