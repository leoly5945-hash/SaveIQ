"""CP7 cross-merchant comparison cache: merchant_comparisons

Revision ID: 202609090001
Revises: 202609070001
Create Date: 2026-09-09 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202609090001"
down_revision: str | None = "202609070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "merchant_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_product_id", sa.String(length=180), nullable=False),
        sa.Column("market", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("keyword", sa.String(length=512), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("offers_json", sa.JSON(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
            name="uq_merchant_comparisons_provider_id_market",
        ),
    )
    op.create_index(
        "ix_merchant_comparisons_status",
        "merchant_comparisons",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_merchant_comparisons_status", table_name="merchant_comparisons")
    op.drop_table("merchant_comparisons")
