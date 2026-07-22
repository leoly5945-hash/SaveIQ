from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class RecordStatus(StrEnum):
    active = "active"
    inactive = "inactive"
    expired = "expired"
    rejected = "rejected"


class FreshnessStatus(StrEnum):
    fresh = "fresh"
    stale = "stale"
    unknown = "unknown"


class IdentifierType(StrEnum):
    upc = "upc"
    ean = "ean"
    gtin = "gtin"
    isbn = "isbn"
    mpn = "mpn"
    merchant_sku = "merchant_sku"
    provider_product_id = "provider_product_id"


class RawRecordStatus(StrEnum):
    received = "received"
    normalized = "normalized"
    duplicate = "duplicate"
    stale = "stale"
    rejected = "rejected"
    error = "error"


class SyncJobStatus(StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"
    completed_with_errors = "completed_with_errors"


class ClickTargetType(StrEnum):
    product = "product"
    affiliate = "affiliate"


def enum_column(enum_type: type[StrEnum], *, default: StrEnum | None = None) -> Mapped[str]:
    return mapped_column(
        Enum(enum_type, native_enum=False, validate_strings=True),
        nullable=False,
        default=default.value if default else None,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SourceAttributionMixin:
    provider_source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_successful_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness_status: Mapped[str] = enum_column(FreshnessStatus, default=FreshnessStatus.fresh)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    market: Mapped[str] = mapped_column(String(2), nullable=False)
    record_status: Mapped[str] = enum_column(RecordStatus, default=RecordStatus.active)


class AffiliateProvider(Base, TimestampMixin):
    __tablename__ = "affiliate_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    market: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    raw_records: Mapped[list[RawProviderRecord]] = relationship(back_populates="provider")
    sync_jobs: Mapped[list[AffiliateSyncJob]] = relationship(back_populates="provider")


class Merchant(Base, TimestampMixin):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    market: Mapped[str] = mapped_column(String(2), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(2048))

    listings: Mapped[list[MerchantListing]] = relationship(back_populates="merchant")


class Brand(Base, TimestampMixin):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)

    products: Mapped[list[CanonicalProduct]] = relationship(back_populates="brand")


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))

    parent: Mapped[Category | None] = relationship(remote_side=[id])
    products: Mapped[list[CanonicalProduct]] = relationship(back_populates="category")


class CanonicalProduct(Base, TimestampMixin):
    __tablename__ = "canonical_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    mpn: Mapped[str | None] = mapped_column(String(160))
    resolution_status: Mapped[str] = mapped_column(String(40), nullable=False, default="resolved")
    review_reason: Mapped[str | None] = mapped_column(String(300))

    brand: Mapped[Brand | None] = relationship(back_populates="products")
    category: Mapped[Category | None] = relationship(back_populates="products")
    identifiers: Mapped[list[ProductIdentifier]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    listings: Mapped[list[MerchantListing]] = relationship(back_populates="canonical_product")

    __table_args__ = (
        UniqueConstraint("brand_id", "mpn", name="uq_canonical_products_brand_mpn"),
        Index("ix_canonical_products_title", "title"),
    )


class ProductIdentifier(Base, TimestampMixin):
    __tablename__ = "product_identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_product_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    identifier_type: Mapped[str] = enum_column(IdentifierType)
    identifier_value: Mapped[str] = mapped_column(String(180), nullable=False)
    provider_source: Mapped[str | None] = mapped_column(String(64))
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"))

    product: Mapped[CanonicalProduct] = relationship(back_populates="identifiers")

    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "identifier_value",
            "provider_source",
            name="uq_product_identifiers_type_value_provider",
        ),
        Index("ix_product_identifiers_lookup", "identifier_type", "identifier_value"),
    )


class MerchantListing(Base, TimestampMixin, SourceAttributionMixin):
    __tablename__ = "merchant_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_product_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    merchant_sku: Mapped[str | None] = mapped_column(String(160))
    provider_product_id: Mapped[str] = mapped_column(String(180), nullable=False)
    product_url: Mapped[str | None] = mapped_column(String(2048))
    provider_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    canonical_product: Mapped[CanonicalProduct] = relationship(back_populates="listings")
    merchant: Mapped[Merchant] = relationship(back_populates="listings")
    offers: Mapped[list[Offer]] = relationship(back_populates="listing")
    price_history: Mapped[list[PriceHistory]] = relationship(back_populates="listing")

    __table_args__ = (
        UniqueConstraint("provider_source", "source_record_id", name="uq_listing_source_record"),
        UniqueConstraint(
            "provider_source",
            "provider_product_id",
            "merchant_id",
            name="uq_listing_provider_product_merchant",
        ),
        Index("ix_merchant_listings_product", "canonical_product_id"),
    )


class Offer(Base, TimestampMixin, SourceAttributionMixin):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_listing_id: Mapped[int] = mapped_column(
        ForeignKey("merchant_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_price_cents: Mapped[int | None] = mapped_column(Integer)
    availability: Mapped[str] = mapped_column(String(40), nullable=False, default="in_stock")
    affiliate_link_id: Mapped[int | None] = mapped_column(ForeignKey("affiliate_links.id"))

    listing: Mapped[MerchantListing] = relationship(back_populates="offers")
    affiliate_link: Mapped[AffiliateLink | None] = relationship(back_populates="offers")

    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_offers_price_non_negative"),
        UniqueConstraint("provider_source", "source_record_id", name="uq_offers_source_record"),
        Index("ix_offers_listing", "merchant_listing_id"),
    )


class PriceHistory(Base, TimestampMixin, SourceAttributionMixin):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_listing_id: Mapped[int] = mapped_column(
        ForeignKey("merchant_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_price_cents: Mapped[int | None] = mapped_column(Integer)

    listing: Mapped[MerchantListing] = relationship(back_populates="price_history")

    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_price_history_price_non_negative"),
        UniqueConstraint(
            "merchant_listing_id",
            "observed_at",
            "price_cents",
            "sale_price_cents",
            name="uq_price_history_append_guard",
        ),
        Index("ix_price_history_listing_observed", "merchant_listing_id", "observed_at"),
    )


class Coupon(Base, TimestampMixin, SourceAttributionMixin):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(40), nullable=False)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_expired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("provider_source", "source_record_id", name="uq_coupons_source_record"),
        Index("ix_coupons_merchant", "merchant_id"),
    )


class CashbackOffer(Base, TimestampMixin, SourceAttributionMixin):
    __tablename__ = "cashback_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    rate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    rate_value_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("provider_source", "source_record_id", name="uq_cashback_source_record"),
        Index("ix_cashback_merchant", "merchant_id"),
    )


class AffiliateLink(Base, TimestampMixin, SourceAttributionMixin):
    __tablename__ = "affiliate_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    destination_url: Mapped[str | None] = mapped_column(String(2048))

    offers: Mapped[list[Offer]] = relationship(back_populates="affiliate_link")

    __table_args__ = (
        UniqueConstraint("provider_source", "source_record_id", name="uq_affiliate_links_source"),
    )


class AffiliateClickEvent(Base):
    __tablename__ = "affiliate_click_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id", ondelete="SET NULL"))
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"))
    merchant_listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_listings.id", ondelete="SET NULL")
    )
    target_type: Mapped[str] = enum_column(ClickTargetType)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    provider_source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(String(160), nullable=False)
    market: Mapped[str] = mapped_column(String(2), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    referrer: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    offer: Mapped[Offer | None] = relationship()
    merchant: Mapped[Merchant | None] = relationship()
    listing: Mapped[MerchantListing | None] = relationship()

    __table_args__ = (Index("ix_affiliate_click_events_offer_created", "offer_id", "created_at"),)


class AffiliateSyncJob(Base, TimestampMixin):
    __tablename__ = "affiliate_sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("affiliate_providers.id", ondelete="CASCADE")
    )
    status: Mapped[str] = enum_column(SyncJobStatus, default=SyncJobStatus.running)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    provider: Mapped[AffiliateProvider] = relationship(back_populates="sync_jobs")
    errors: Mapped[list[AffiliateSyncError]] = relationship(back_populates="sync_job")
    raw_records: Mapped[list[RawProviderRecord]] = relationship(back_populates="sync_job")


class AffiliateSyncError(Base, TimestampMixin):
    __tablename__ = "affiliate_sync_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sync_job_id: Mapped[int] = mapped_column(
        ForeignKey("affiliate_sync_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(160))
    error_code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)

    sync_job: Mapped[AffiliateSyncJob] = relationship(back_populates="errors")


class RawProviderRecord(Base, TimestampMixin):
    __tablename__ = "raw_provider_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("affiliate_providers.id", ondelete="CASCADE")
    )
    sync_job_id: Mapped[int] = mapped_column(
        ForeignKey("affiliate_sync_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_record_id: Mapped[str] = mapped_column(String(160), nullable=False)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = enum_column(RawRecordStatus, default=RawRecordStatus.received)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    provider: Mapped[AffiliateProvider] = relationship(back_populates="raw_records")
    sync_job: Mapped[AffiliateSyncJob] = relationship(back_populates="raw_records")

    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "source_record_id",
            "record_hash",
            name="uq_raw_provider_record_dedupe",
        ),
        Index("ix_raw_provider_records_provider_source", "provider_id", "source_record_id"),
    )
