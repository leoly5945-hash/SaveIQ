"""recommendation trace events

Revision ID: 202607100004
Revises: 202607100003
Create Date: 2026-07-25 00:04:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607100004"
down_revision: str | None = "202607100003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_trace_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy", sa.String(length=80), nullable=False),
        sa.Column("raw_intent", sa.String(length=240), nullable=False),
        sa.Column("parsed_intent", sa.JSON(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("recommended_offer_ids", sa.JSON(), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_recommendation_trace_events_created",
        "recommendation_trace_events",
        ["created_at"],
    )
    op.create_index(
        "ix_recommendation_trace_events_strategy",
        "recommendation_trace_events",
        ["strategy"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_trace_events_strategy",
        table_name="recommendation_trace_events",
    )
    op.drop_index(
        "ix_recommendation_trace_events_created",
        table_name="recommendation_trace_events",
    )
    op.drop_table("recommendation_trace_events")
