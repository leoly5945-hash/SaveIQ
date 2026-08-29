"""affiliate click attribution: subid on clicks + conversions table

Revision ID: 202608280001
Revises: 202608080001
Create Date: 2026-08-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202608280001"
down_revision: str | None = "202608080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "affiliate_click_events",
        sa.Column("click_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "affiliate_click_events",
        sa.Column("subid", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "affiliate_click_events",
        sa.Column("network", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "affiliate_click_events",
        sa.Column("landing_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "affiliate_click_events",
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "affiliate_click_events",
        sa.Column(
            "is_bot",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "uq_affiliate_click_events_click_id",
        "affiliate_click_events",
        ["click_id"],
        unique=True,
    )
    op.create_index(
        "ix_affiliate_click_events_network",
        "affiliate_click_events",
        ["network"],
    )

    op.create_table(
        "affiliate_conversions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("network", sa.String(length=64), nullable=False),
        sa.Column("subid", sa.String(length=80), nullable=True),
        sa.Column("click_event_id", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("order_id", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("order_value_cents", sa.Integer(), nullable=True),
        sa.Column("commission_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["click_event_id"],
            ["affiliate_click_events.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "network",
            "external_id",
            name="uq_affiliate_conversions_network_ext",
        ),
    )
    op.create_index(
        "ix_affiliate_conversions_network",
        "affiliate_conversions",
        ["network"],
    )
    op.create_index(
        "ix_affiliate_conversions_subid",
        "affiliate_conversions",
        ["subid"],
    )
    op.create_index(
        "ix_affiliate_conversions_reported",
        "affiliate_conversions",
        ["network", "reported_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_affiliate_conversions_reported", table_name="affiliate_conversions")
    op.drop_index("ix_affiliate_conversions_subid", table_name="affiliate_conversions")
    op.drop_index("ix_affiliate_conversions_network", table_name="affiliate_conversions")
    op.drop_table("affiliate_conversions")
    op.drop_index(
        "ix_affiliate_click_events_network",
        table_name="affiliate_click_events",
    )
    op.drop_index(
        "uq_affiliate_click_events_click_id",
        table_name="affiliate_click_events",
    )
    op.drop_column("affiliate_click_events", "is_bot")
    op.drop_column("affiliate_click_events", "ip_hash")
    op.drop_column("affiliate_click_events", "landing_url")
    op.drop_column("affiliate_click_events", "network")
    op.drop_column("affiliate_click_events", "subid")
    op.drop_column("affiliate_click_events", "click_id")
