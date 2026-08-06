"""Gate 8 personalization tables

Revision ID: 202608080001
Revises: 202608060001
Create Date: 2026-08-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202608080001"
down_revision: str | None = "202608060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anonymous_users",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_active",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "preferences",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "preferred_categories",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("avg_query_length", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_feedback", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "personalization_opt_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "embedding",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "click_history",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.create_index("ix_anonymous_users_last_active", "anonymous_users", ["last_active"])

    op.create_table(
        "user_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("query_text", sa.String(length=240), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["anonymous_users.user_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_user_events_user_id", "user_events", ["user_id"])
    op.create_index("ix_user_events_user_created", "user_events", ["user_id", "created_at"])
    op.create_index("ix_user_events_type", "user_events", ["event_type"])

    op.add_column(
        "affiliate_click_events",
        sa.Column("anonymous_user_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_affiliate_click_events_anonymous_user",
        "affiliate_click_events",
        ["anonymous_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_affiliate_click_events_anonymous_user",
        table_name="affiliate_click_events",
    )
    op.drop_column("affiliate_click_events", "anonymous_user_id")
    op.drop_index("ix_user_events_type", table_name="user_events")
    op.drop_index("ix_user_events_user_created", table_name="user_events")
    op.drop_index("ix_user_events_user_id", table_name="user_events")
    op.drop_table("user_events")
    op.drop_index("ix_anonymous_users_last_active", table_name="anonymous_users")
    op.drop_table("anonymous_users")
