"""affiliate domain foundation

Revision ID: 202607100002
Revises: 202607100001
Create Date: 2026-07-10 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607100002"
down_revision: str | None = "202607100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def source_columns() -> list[sa.Column]:
    return [
        sa.Column("provider_source", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingestion_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_successful_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness_status", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("market", sa.String(length=2), nullable=False),
        sa.Column("record_status", sa.String(length=20), nullable=False),
    ]


def timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "affiliate_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("market", sa.String(length=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("source", name="uq_affiliate_providers_source"),
    )
    op.create_table(
        "merchants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("market", sa.String(length=2), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("slug", name="uq_merchants_slug"),
    )
    op.create_table(
        "brands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("name", name="uq_brands_name"),
        sa.UniqueConstraint("normalized_name", name="uq_brands_normalized_name"),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
    )
    op.create_table(
        "canonical_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("mpn", sa.String(length=160), nullable=True),
        sa.Column("resolution_status", sa.String(length=40), nullable=False),
        sa.Column("review_reason", sa.String(length=300), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("brand_id", "mpn", name="uq_canonical_products_brand_mpn"),
    )
    op.create_index("ix_canonical_products_title", "canonical_products", ["title"])
    op.create_table(
        "product_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_product_id", sa.Integer(), nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier_value", sa.String(length=180), nullable=False),
        sa.Column("provider_source", sa.String(length=64), nullable=True),
        sa.Column("merchant_id", sa.Integer(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["canonical_product_id"],
            ["canonical_products.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier_value",
            "provider_source",
            name="uq_product_identifiers_type_value_provider",
        ),
    )
    op.create_index(
        "ix_product_identifiers_lookup",
        "product_identifiers",
        ["identifier_type", "identifier_value"],
    )
    op.create_table(
        "merchant_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_product_id", sa.Integer(), nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("merchant_sku", sa.String(length=160), nullable=True),
        sa.Column("provider_product_id", sa.String(length=180), nullable=False),
        sa.Column("product_url", sa.String(length=2048), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=True),
        *source_columns(),
        *timestamps(),
        sa.ForeignKeyConstraint(["canonical_product_id"], ["canonical_products.id"]),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.UniqueConstraint("provider_source", "source_record_id", name="uq_listing_source_record"),
        sa.UniqueConstraint(
            "provider_source",
            "provider_product_id",
            "merchant_id",
            name="uq_listing_provider_product_merchant",
        ),
    )
    op.create_index("ix_merchant_listings_product", "merchant_listings", ["canonical_product_id"])
    op.create_index(
        "ix_merchant_listings_provider_source",
        "merchant_listings",
        ["provider_source"],
    )
    op.create_table(
        "affiliate_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("destination_url", sa.String(length=2048), nullable=True),
        *source_columns(),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider_source",
            "source_record_id",
            name="uq_affiliate_links_source",
        ),
    )
    op.create_index("ix_affiliate_links_provider_source", "affiliate_links", ["provider_source"])
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_listing_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("sale_price_cents", sa.Integer(), nullable=True),
        sa.Column("availability", sa.String(length=40), nullable=False),
        sa.Column("affiliate_link_id", sa.Integer(), nullable=True),
        *source_columns(),
        *timestamps(),
        sa.CheckConstraint("price_cents >= 0", name="ck_offers_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["merchant_listing_id"],
            ["merchant_listings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["affiliate_link_id"], ["affiliate_links.id"]),
        sa.UniqueConstraint("provider_source", "source_record_id", name="uq_offers_source_record"),
    )
    op.create_index("ix_offers_listing", "offers", ["merchant_listing_id"])
    op.create_index("ix_offers_provider_source", "offers", ["provider_source"])
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_listing_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("sale_price_cents", sa.Integer(), nullable=True),
        *source_columns(),
        *timestamps(),
        sa.CheckConstraint("price_cents >= 0", name="ck_price_history_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["merchant_listing_id"],
            ["merchant_listings.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "merchant_listing_id",
            "observed_at",
            "price_cents",
            "sale_price_cents",
            name="uq_price_history_append_guard",
        ),
    )
    op.create_index(
        "ix_price_history_listing_observed",
        "price_history",
        ["merchant_listing_id", "observed_at"],
    )
    op.create_index("ix_price_history_provider_source", "price_history", ["provider_source"])
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("discount_type", sa.String(length=40), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_expired", sa.Boolean(), nullable=False),
        *source_columns(),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider_source", "source_record_id", name="uq_coupons_source_record"),
    )
    op.create_index("ix_coupons_merchant", "coupons", ["merchant_id"])
    op.create_index("ix_coupons_provider_source", "coupons", ["provider_source"])
    op.create_table(
        "cashback_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("rate_type", sa.String(length=40), nullable=False),
        sa.Column("rate_value_bps", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *source_columns(),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider_source",
            "source_record_id",
            name="uq_cashback_source_record",
        ),
    )
    op.create_index("ix_cashback_merchant", "cashback_offers", ["merchant_id"])
    op.create_index("ix_cashback_offers_provider_source", "cashback_offers", ["provider_source"])
    op.create_table(
        "affiliate_sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("stale_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["provider_id"], ["affiliate_providers.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "affiliate_sync_errors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sync_job_id", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["sync_job_id"], ["affiliate_sync_jobs.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "raw_provider_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("sync_job_id", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("record_hash", sa.String(length=120), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["provider_id"], ["affiliate_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_job_id"], ["affiliate_sync_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider_id",
            "source_record_id",
            "record_hash",
            name="uq_raw_provider_record_dedupe",
        ),
    )
    op.create_index(
        "ix_raw_provider_records_provider_source",
        "raw_provider_records",
        ["provider_id", "source_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_raw_provider_records_provider_source", table_name="raw_provider_records")
    op.drop_table("raw_provider_records")
    op.drop_table("affiliate_sync_errors")
    op.drop_table("affiliate_sync_jobs")
    op.drop_index("ix_cashback_offers_provider_source", table_name="cashback_offers")
    op.drop_index("ix_cashback_merchant", table_name="cashback_offers")
    op.drop_table("cashback_offers")
    op.drop_index("ix_coupons_provider_source", table_name="coupons")
    op.drop_index("ix_coupons_merchant", table_name="coupons")
    op.drop_table("coupons")
    op.drop_index("ix_price_history_provider_source", table_name="price_history")
    op.drop_index("ix_price_history_listing_observed", table_name="price_history")
    op.drop_table("price_history")
    op.drop_index("ix_offers_provider_source", table_name="offers")
    op.drop_index("ix_offers_listing", table_name="offers")
    op.drop_table("offers")
    op.drop_index("ix_affiliate_links_provider_source", table_name="affiliate_links")
    op.drop_table("affiliate_links")
    op.drop_index("ix_merchant_listings_provider_source", table_name="merchant_listings")
    op.drop_index("ix_merchant_listings_product", table_name="merchant_listings")
    op.drop_table("merchant_listings")
    op.drop_index("ix_product_identifiers_lookup", table_name="product_identifiers")
    op.drop_table("product_identifiers")
    op.drop_index("ix_canonical_products_title", table_name="canonical_products")
    op.drop_table("canonical_products")
    op.drop_table("categories")
    op.drop_table("brands")
    op.drop_table("merchants")
    op.drop_table("affiliate_providers")
