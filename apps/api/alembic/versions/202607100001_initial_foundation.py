"""initial foundation

Revision ID: 202607100001
Revises:
Create Date: 2026-07-10 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "202607100001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("merchant_name", sa.String(length=256), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("affiliate_url", sa.String(length=2048), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_products_source", "products", ["source"])
    op.create_index("ix_products_title", "products", ["title"])


def downgrade() -> None:
    op.drop_index("ix_products_title", table_name="products")
    op.drop_index("ix_products_source", table_name="products")
    op.drop_table("products")
