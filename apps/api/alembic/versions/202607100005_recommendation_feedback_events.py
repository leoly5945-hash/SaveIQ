"""recommendation feedback events

Revision ID: 202607100005
Revises: 202607100004
Create Date: 2026-07-25 01:12:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607100005"
down_revision: str | None = "202607100004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trace_event_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.String(length=11), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("provider_source", sa.String(length=64), nullable=True),
        sa.Column("market", sa.String(length=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offers.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trace_event_id"],
            ["recommendation_trace_events.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_recommendation_feedback_events_created",
        "recommendation_feedback_events",
        ["created_at"],
    )
    op.create_index(
        "ix_recommendation_feedback_events_provider_source",
        "recommendation_feedback_events",
        ["provider_source"],
    )
    op.create_index(
        "ix_recommendation_feedback_events_rating",
        "recommendation_feedback_events",
        ["rating"],
    )
    op.create_index(
        "ix_recommendation_feedback_events_trace",
        "recommendation_feedback_events",
        ["trace_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_feedback_events_trace",
        table_name="recommendation_feedback_events",
    )
    op.drop_index(
        "ix_recommendation_feedback_events_rating",
        table_name="recommendation_feedback_events",
    )
    op.drop_index(
        "ix_recommendation_feedback_events_provider_source",
        table_name="recommendation_feedback_events",
    )
    op.drop_index(
        "ix_recommendation_feedback_events_created",
        table_name="recommendation_feedback_events",
    )
    op.drop_table("recommendation_feedback_events")
