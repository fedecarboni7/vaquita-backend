"""add email authentication

Revision ID: c8d9e0f1a2b3
Revises: a7c4e1f9b2d6
Create Date: 2026-10-03 00:00:00.000000

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "a7c4e1f9b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "google_id", existing_type=sa.String(length=255), nullable=True)
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute(sa.text("UPDATE users SET email_verified = TRUE"))
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_tokens_user_id"), "auth_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_auth_tokens_token_hash"), "auth_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_tokens_token_hash"), table_name="auth_tokens")
    op.drop_index(op.f("ix_auth_tokens_user_id"), table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "password_hash")
    op.alter_column("users", "google_id", existing_type=sa.String(length=255), nullable=False)
