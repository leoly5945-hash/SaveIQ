"""bandit logs

Revision ID: 202608060001
Revises: 202607100006
Create Date: 2026-08-06 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202608060001"
down_revision: str | None = "202607100006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bandit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("reward", sa.Float(), nullable=True),
        sa.Column("user_id", sa.String(length=120), nullable=True),
        sa.Column("rule_action", sa.String(length=64), nullable=True),
        sa.Column("bandit_action", sa.String(length=64), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("explored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_bandit_logs_created", "bandit_logs", ["created_at"])
    op.create_index("ix_bandit_logs_action", "bandit_logs", ["action"])
    op.create_index("ix_bandit_logs_mode", "bandit_logs", ["mode"])


def downgrade() -> None:
    op.drop_index("ix_bandit_logs_mode", table_name="bandit_logs")
    op.drop_index("ix_bandit_logs_action", table_name="bandit_logs")
    op.drop_index("ix_bandit_logs_created", table_name="bandit_logs")
    op.drop_table("bandit_logs")
