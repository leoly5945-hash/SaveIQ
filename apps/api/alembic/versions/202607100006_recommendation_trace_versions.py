"""recommendation trace versions

Revision ID: 202607100006
Revises: 202607100005
Create Date: 2026-07-27 02:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607100006"
down_revision: str | None = "202607100005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recommendation_trace_events",
        sa.Column(
            "rule_version",
            sa.String(length=80),
            server_default="ruleset-2026-07-27-gate-4o",
            nullable=False,
        ),
    )
    op.add_column(
        "recommendation_trace_events",
        sa.Column(
            "intent_parser_version",
            sa.String(length=80),
            server_default="intent-parser-v0",
            nullable=False,
        ),
    )
    op.add_column(
        "recommendation_trace_events",
        sa.Column(
            "ranker_version",
            sa.String(length=80),
            server_default="ranker-v0",
            nullable=False,
        ),
    )
    op.add_column(
        "recommendation_trace_events",
        sa.Column(
            "fixture_set_version",
            sa.String(length=80),
            server_default="fixtures-v0",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_recommendation_trace_events_rule_version",
        "recommendation_trace_events",
        ["rule_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_trace_events_rule_version",
        table_name="recommendation_trace_events",
    )
    op.drop_column("recommendation_trace_events", "fixture_set_version")
    op.drop_column("recommendation_trace_events", "ranker_version")
    op.drop_column("recommendation_trace_events", "intent_parser_version")
    op.drop_column("recommendation_trace_events", "rule_version")
