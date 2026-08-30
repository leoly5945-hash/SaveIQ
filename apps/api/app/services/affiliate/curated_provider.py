"""Curated Amazon.ca affiliate feed.

Unlike :mod:`app.services.affiliate.mock_provider` (deterministic fixtures for
staging), this adapter emits a small set of *real* Amazon.ca products that we
hand-picked and price-checked by hand. The catalogue lives in
``curated_deals.json`` next to this module so a non-engineer can add rows
without touching Python.

Each entry becomes a normalized product offer whose affiliate URL carries our
Amazon Associates tag (``AMAZON_ASSOCIATE_TAG``, default ``saveiq-20``). The
outbound ``/go`` redirect then appends the per-click ``ascsubtag`` SubID for
reconciliation. Prices are a point-in-time snapshot: the ``price_checked`` date
and a short blurb travel through ``provider_metadata`` so the UI can label the
card honestly ("price checked <date> - confirm at Amazon.ca") and never claims a
discount or a "lowest price".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.settings import get_settings
from app.services.affiliate.schemas import (
    NormalizedProductOffer,
    NormalizedRecord,
    ProviderConnectionResult,
    ProviderMerchant,
    ProviderRawRecord,
    ProviderRecordType,
    ProviderValidationResult,
)

CURATED_DEALS_PATH = Path(__file__).with_name("curated_deals.json")

# One clock per process so re-syncs produce identical hashes/timestamps and stay
# inside the 30-day ingestion freshness window.
_FEED_NOW = datetime.now(UTC)

_REQUIRED_PAYLOAD_FIELDS = (
    "merchant_slug",
    "provider_product_id",
    "title",
    "brand_name",
    "category_name",
    "category_slug",
    "price_cents",
    "currency",
    "market",
    "affiliate_url",
)


def _load_catalogue(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("deals"), list):
        raise ValueError(f"{path} must be a JSON object with a 'deals' array")
    return data


class CuratedAmazonProvider:
    """Adapter over a hand-maintained JSON list of real Amazon.ca products."""

    source = "amazon_ca"
    name = "Amazon.ca (curated)"
    market = "CA"
    currency = "CAD"

    def __init__(
        self,
        *,
        catalogue_path: Path | None = None,
        associate_tag: str | None = None,
        now: datetime | None = None,
    ) -> None:
        self._path = catalogue_path or CURATED_DEALS_PATH
        self._tag = associate_tag or get_settings().amazon_associate_tag
        self._now = now or _FEED_NOW
        catalogue = _load_catalogue(self._path)
        self._retailer = str(catalogue.get("retailer", "Amazon.ca"))
        self._retailer_slug = str(catalogue.get("retailer_slug", "amazon-ca"))
        self._retailer_url = str(catalogue.get("retailer_url", "https://www.amazon.ca"))
        self._currency = str(catalogue.get("currency", self.currency))
        self._market = str(catalogue.get("market", self.market))
        self._merchant = ProviderMerchant(
            source_record_id=f"merchant-{self._retailer_slug}",
            name=self._retailer,
            slug=self._retailer_slug,
            market=self._market,
            website_url=self._retailer_url,
        )
        self._records = self._build_records(catalogue["deals"])

    # -- adapter protocol ---------------------------------------------------

    async def test_connection(self) -> ProviderConnectionResult:
        return ProviderConnectionResult(
            ok=True,
            message=f"Curated feed ready ({len(self._records)} products)",
        )

    async def fetch_merchants(self) -> list[ProviderMerchant]:
        return [self._merchant]

    async def fetch_products(self) -> list[ProviderRawRecord]:
        return list(self._records)

    async def fetch_offers(self) -> list[ProviderRawRecord]:
        return list(self._records)

    async def fetch_prices(self) -> list[ProviderRawRecord]:
        return list(self._records)

    async def fetch_coupons(self) -> list[ProviderRawRecord]:
        return []

    async def fetch_cashback(self) -> list[ProviderRawRecord]:
        return []

    async def fetch_incremental_updates(self) -> list[ProviderRawRecord]:
        return list(self._records)

    def validate_record(self, record: ProviderRawRecord) -> ProviderValidationResult:
        payload = record.payload
        missing = [field for field in _REQUIRED_PAYLOAD_FIELDS if payload.get(field) in (None, "")]
        if missing:
            return ProviderValidationResult(
                is_valid=False,
                error_code="missing_required_field",
                message=f"Missing required fields: {', '.join(missing)}",
            )
        if int(payload["price_cents"]) <= 0:
            return ProviderValidationResult(
                is_valid=False,
                error_code="invalid_price",
                message="price_cents must be a positive integer.",
            )
        return ProviderValidationResult(is_valid=True)

    def normalize_record(self, record: ProviderRawRecord) -> NormalizedRecord:
        payload = record.payload
        return NormalizedProductOffer(
            source_record_id=record.source_record_id,
            provider_product_id=str(payload["provider_product_id"]),
            source_timestamp=record.source_timestamp,
            merchant=self._merchant,
            brand_name=str(payload["brand_name"]),
            category_name=str(payload["category_name"]),
            category_slug=str(payload["category_slug"]),
            title=str(payload["title"]),
            description=payload.get("blurb"),
            mpn=str(payload["provider_product_id"]),
            merchant_sku=str(payload["provider_product_id"]),
            identifiers=[],
            price_cents=int(payload["price_cents"]),
            sale_price_cents=None,
            currency=str(payload["currency"]),
            market=str(payload["market"]),
            product_url=str(payload["product_url"]),
            affiliate_url=str(payload["affiliate_url"]),
            availability="in_stock",
            provider_metadata={
                "curated": True,
                "retailer": self._retailer,
                "asin": str(payload["provider_product_id"]),
                "price_checked": payload.get("price_checked"),
                "blurb": payload.get("blurb"),
            },
        )

    # -- record construction ---------------------------------------------------

    def _build_records(self, deals: list[dict[str, Any]]) -> list[ProviderRawRecord]:
        records: list[ProviderRawRecord] = []
        for deal in deals:
            asin = str(deal["asin"]).strip()
            records.append(
                ProviderRawRecord(
                    source_record_id=f"curated-{asin}",
                    record_type=ProviderRecordType.product_offer,
                    source_timestamp=self._now,
                    payload={
                        "merchant_slug": self._retailer_slug,
                        "provider_product_id": asin,
                        "title": str(deal["title"]).strip(),
                        "brand_name": str(deal["brand"]).strip(),
                        "category_name": str(deal["category"]).strip(),
                        "category_slug": str(deal["category_slug"]).strip(),
                        "price_cents": int(deal["price_cents"]),
                        "currency": self._currency,
                        "market": self._market,
                        "product_url": f"https://www.amazon.ca/dp/{asin}",
                        "affiliate_url": f"https://www.amazon.ca/dp/{asin}?tag={self._tag}",
                        "price_checked": deal.get("price_checked"),
                        "blurb": (str(deal["blurb"]).strip() if deal.get("blurb") else None),
                    },
                )
            )
        return records
