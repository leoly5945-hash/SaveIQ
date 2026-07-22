"""affiliate click events

Revision ID: 202607100003
Revises: 202607100002
Create Date: 2026-07-22 00:03:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607100003"
down_revision: str | None = "202607100002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "affiliate_click_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("merchant_id", sa.Integer(), nullable=True),
        sa.Column("merchant_listing_id", sa.Integer(), nullable=True),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("provider_source", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=False),
        sa.Column("market", sa.String(length=2), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("referrer", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["merchant_listing_id"],
            ["merchant_listings.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_affiliate_click_events_offer_created",
        "affiliate_click_events",
        ["offer_id", "created_at"],
    )
    op.create_index(
        "ix_affiliate_click_events_provider_source",
        "affiliate_click_events",
        ["provider_source"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_affiliate_click_events_provider_source",
        table_name="affiliate_click_events",
    )
    op.drop_index(
        "ix_affiliate_click_events_offer_created",
        table_name="affiliate_click_events",
    )
    op.drop_table("affiliate_click_events")
