"""CP15 price alerts: tracked_products, price_observations, price_alerts

Revision ID: 202609070001
Revises: 202608280001
Create Date: 2026-09-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202609070001"
down_revision: str | None = "202608280001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracked_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_product_id", sa.String(length=180), nullable=False),
        sa.Column("market", sa.String(length=2), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("product_url", sa.String(length=2048), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_product_id",
            "market",
            name="uq_tracked_products_provider_id_market",
        ),
    )

    op.create_table(
        "price_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tracked_product_id",
            sa.Integer(),
            sa.ForeignKey("tracked_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("avg90_cents", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.String(length=16), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tracked_product_id",
            "observed_at",
            name="uq_price_observations_tracked_observed",
        ),
    )
    op.create_index(
        "ix_price_observations_tracked_observed",
        "price_observations",
        ["tracked_product_id", "observed_at"],
    )

    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tracked_product_id",
            sa.Integer(),
            sa.ForeignKey("tracked_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("threshold_cents", sa.Integer(), nullable=True),
        sa.Column("baseline_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=False),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("unsubscribe_token", name="uq_price_alerts_unsub_token"),
    )
    op.create_index("ix_price_alerts_tracked", "price_alerts", ["tracked_product_id"])
    op.create_index("ix_price_alerts_email", "price_alerts", ["email"])
    op.create_index("ix_price_alerts_status", "price_alerts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_price_alerts_status", table_name="price_alerts")
    op.drop_index("ix_price_alerts_email", table_name="price_alerts")
    op.drop_index("ix_price_alerts_tracked", table_name="price_alerts")
    op.drop_table("price_alerts")
    op.drop_index("ix_price_observations_tracked_observed", table_name="price_observations")
    op.drop_table("price_observations")
    op.drop_table("tracked_products")
