"""keep latest usage row per user and usage type

Revision ID: f2c3d4e5a6b7
Revises: d8f17a1b9c23
Create Date: 2026-04-27 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f2c3d4e5a6b7"
down_revision: Union[str, None] = "d8f17a1b9c23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep only the latest day row per (user_id, usage_type) before tightening PK.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                ctid,
                row_number() OVER (
                    PARTITION BY user_id, usage_type
                    ORDER BY date DESC
                ) AS rn
            FROM agent_usage
        )
        DELETE FROM agent_usage au
        USING ranked r
        WHERE au.ctid = r.ctid
          AND r.rn > 1;
        """
    )

    op.drop_constraint("pk_agent_usage_user_date_type", "agent_usage", type_="primary")
    op.create_primary_key(
        "pk_agent_usage_user_type",
        "agent_usage",
        ["user_id", "usage_type"],
    )


def downgrade() -> None:
    op.drop_constraint("pk_agent_usage_user_type", "agent_usage", type_="primary")
    op.create_primary_key(
        "pk_agent_usage_user_date_type",
        "agent_usage",
        ["user_id", "date", "usage_type"],
    )
