"""split agent_usage by usage type

Revision ID: d8f17a1b9c23
Revises: b4b49cfe10bf
Create Date: 2026-04-26 11:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8f17a1b9c23"
down_revision: Union[str, None] = "b4b49cfe10bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    usage_type_enum = sa.Enum("chat", "transcribe", name="usage_type")
    usage_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "agent_usage",
        sa.Column(
            "usage_type",
            usage_type_enum,
            nullable=False,
            server_default=sa.text("'chat'"),
        ),
    )

    op.drop_constraint("pk_agent_usage_user_date", "agent_usage", type_="primary")
    op.create_primary_key(
        "pk_agent_usage_user_date_type",
        "agent_usage",
        ["user_id", "date", "usage_type"],
    )

    op.alter_column("agent_usage", "usage_type", server_default=None)


def downgrade() -> None:
    op.drop_constraint("pk_agent_usage_user_date_type", "agent_usage", type_="primary")
    op.create_primary_key("pk_agent_usage_user_date", "agent_usage", ["user_id", "date"])

    op.drop_column("agent_usage", "usage_type")

    usage_type_enum = sa.Enum("chat", "transcribe", name="usage_type")
    usage_type_enum.drop(op.get_bind(), checkfirst=True)
