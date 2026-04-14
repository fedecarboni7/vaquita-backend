"""add account foreign keys to transactions

Revision ID: 7c2e9d6a1b45
Revises: f4a1b9c2d3e4
Create Date: 2026-04-13 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c2e9d6a1b45"
down_revision: str | Sequence[str] | None = "f4a1b9c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.add_column("transactions", sa.Column("account_destination_id", sa.Uuid(), nullable=True))

    op.create_index("ix_transactions_account_id", "transactions", ["account_id"], unique=False)
    op.create_index(
        "ix_transactions_account_destination_id",
        "transactions",
        ["account_destination_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_transactions_account_id_accounts",
        "transactions",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transactions_account_destination_id_accounts",
        "transactions",
        "accounts",
        ["account_destination_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Deterministic backfill for duplicate account names per user:
    # pick the oldest account by created_at and break ties with the smallest id.
    op.execute(
        sa.text(
            """
            WITH ranked_accounts AS (
                SELECT
                    a.id,
                    a.user_id,
                    a.name,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.user_id, a.name
                        ORDER BY a.created_at ASC, a.id ASC
                    ) AS rn
                FROM accounts AS a
            ),
            source_matches AS (
                SELECT
                    t.id AS transaction_id,
                    ra.id AS resolved_account_id
                FROM transactions AS t
                JOIN ranked_accounts AS ra
                    ON ra.user_id = t.user_id
                    AND ra.name = t.account
                    AND ra.rn = 1
                WHERE t.account IS NOT NULL
            )
            UPDATE transactions AS t
            SET account_id = sm.resolved_account_id
            FROM source_matches AS sm
            WHERE t.id = sm.transaction_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked_accounts AS (
                SELECT
                    a.id,
                    a.user_id,
                    a.name,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.user_id, a.name
                        ORDER BY a.created_at ASC, a.id ASC
                    ) AS rn
                FROM accounts AS a
            ),
            destination_matches AS (
                SELECT
                    t.id AS transaction_id,
                    ra.id AS resolved_account_id
                FROM transactions AS t
                JOIN ranked_accounts AS ra
                    ON ra.user_id = t.user_id
                    AND ra.name = t.account_destination
                    AND ra.rn = 1
                WHERE t.account_destination IS NOT NULL
            )
            UPDATE transactions AS t
            SET account_destination_id = dm.resolved_account_id
            FROM destination_matches AS dm
            WHERE t.id = dm.transaction_id
            """
        )
    )

    op.drop_column("transactions", "account_destination")
    op.drop_column("transactions", "account")


def downgrade() -> None:
    op.add_column("transactions", sa.Column("account", sa.String(length=100), nullable=True))
    op.add_column("transactions", sa.Column("account_destination", sa.String(length=100), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE transactions AS t
            SET account = a.name
            FROM accounts AS a
            WHERE t.account_id = a.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE transactions AS t
            SET account_destination = a.name
            FROM accounts AS a
            WHERE t.account_destination_id = a.id
            """
        )
    )

    op.drop_constraint("fk_transactions_account_destination_id_accounts", "transactions", type_="foreignkey")
    op.drop_constraint("fk_transactions_account_id_accounts", "transactions", type_="foreignkey")

    op.drop_index("ix_transactions_account_destination_id", table_name="transactions")
    op.drop_index("ix_transactions_account_id", table_name="transactions")

    op.drop_column("transactions", "account_destination_id")
    op.drop_column("transactions", "account_id")
