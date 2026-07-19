from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator


class ProviderOperation(StrEnum):
    merchants = "merchants"
    products = "products"
    offers = "offers"
    prices = "prices"
    coupons = "coupons"
    cashback = "cashback"
    incremental_updates = "incremental_updates"


class ProviderRecordType(StrEnum):
    product_offer = "product_offer"
    coupon = "coupon"
    cashback = "cashback"


class NormalizedIdentifier(BaseModel):
    identifier_type: str
    identifier_value: str

    @field_validator("identifier_value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        return value.strip().upper()


class ProviderMerchant(BaseModel):
    source_record_id: str
    name: str
    slug: str
    market: str
    website_url: str | None = None


class ProviderRawRecord(BaseModel):
    source_record_id: str
    record_type: ProviderRecordType
    source_timestamp: datetime
    payload: dict[str, Any]


class ProviderValidationResult(BaseModel):
    is_valid: bool
    error_code: str | None = None
    message: str | None = None


class NormalizedProductOffer(BaseModel):
    source_record_id: str
    provider_product_id: str
    source_timestamp: datetime
    merchant: ProviderMerchant
    brand_name: str
    category_name: str
    category_slug: str
    title: str
    description: str | None = None
    mpn: str | None = None
    merchant_sku: str | None = None
    identifiers: list[NormalizedIdentifier] = Field(default_factory=list)
    price_cents: int
    sale_price_cents: int | None = None
    currency: str
    market: str
    product_url: str | None = None
    affiliate_url: str
    availability: str = "in_stock"
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedCoupon(BaseModel):
    source_record_id: str
    source_timestamp: datetime
    merchant: ProviderMerchant
    code: str
    description: str
    discount_type: str
    discount_value: int
    currency: str
    market: str
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class NormalizedCashbackOffer(BaseModel):
    source_record_id: str
    source_timestamp: datetime
    merchant: ProviderMerchant
    rate_type: str
    rate_value_bps: int
    currency: str
    market: str
    starts_at: datetime | None = None
    expires_at: datetime | None = None


NormalizedRecord = NormalizedProductOffer | NormalizedCoupon | NormalizedCashbackOffer


class ProviderConnectionResult(BaseModel):
    ok: bool
    message: str


class AffiliateProviderAdapter(Protocol):
    source: str
    name: str
    market: str
    currency: str

    async def test_connection(self) -> ProviderConnectionResult:
        """Verify that the provider adapter is usable."""

    async def fetch_merchants(self) -> list[ProviderMerchant]:
        """Fetch provider merchants."""

    async def fetch_products(self) -> list[ProviderRawRecord]:
        """Fetch provider product records."""

    async def fetch_offers(self) -> list[ProviderRawRecord]:
        """Fetch provider offer records."""

    async def fetch_prices(self) -> list[ProviderRawRecord]:
        """Fetch provider price records."""

    async def fetch_coupons(self) -> list[ProviderRawRecord]:
        """Fetch provider coupon records."""

    async def fetch_cashback(self) -> list[ProviderRawRecord]:
        """Fetch provider cashback records."""

    async def fetch_incremental_updates(self) -> list[ProviderRawRecord]:
        """Fetch incremental records for a sync run."""

    def validate_record(self, record: ProviderRawRecord) -> ProviderValidationResult:
        """Validate a raw provider record before normalization."""

    def normalize_record(self, record: ProviderRawRecord) -> NormalizedRecord:
        """Normalize a provider record into a typed core schema."""
