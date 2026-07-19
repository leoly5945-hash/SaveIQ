from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.affiliate.schemas import (
    NormalizedCashbackOffer,
    NormalizedCoupon,
    NormalizedIdentifier,
    NormalizedProductOffer,
    NormalizedRecord,
    ProviderConnectionResult,
    ProviderMerchant,
    ProviderRawRecord,
    ProviderRecordType,
    ProviderValidationResult,
)


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


class MockAffiliateProvider:
    source = "mock_ca"
    name = "Mock Canada Affiliate Feed"
    market = "CA"
    currency = "CAD"

    def __init__(self) -> None:
        self._merchants = [
            ProviderMerchant(
                source_record_id="merchant-maple-tech",
                name="Maple Tech",
                slug="maple-tech",
                market=self.market,
                website_url="https://maple-tech.example.test",
            ),
            ProviderMerchant(
                source_record_id="merchant-north-outfitters",
                name="North Outfitters",
                slug="north-outfitters",
                market=self.market,
                website_url="https://north-outfitters.example.test",
            ),
            ProviderMerchant(
                source_record_id="merchant-book-nook",
                name="Book Nook Canada",
                slug="book-nook-canada",
                market=self.market,
                website_url="https://book-nook.example.test",
            ),
        ]
        self._merchant_by_slug = {merchant.slug: merchant for merchant in self._merchants}
        self._records = self._build_records()

    async def test_connection(self) -> ProviderConnectionResult:
        return ProviderConnectionResult(ok=True, message="Mock provider ready")

    async def fetch_merchants(self) -> list[ProviderMerchant]:
        return self._merchants

    async def fetch_products(self) -> list[ProviderRawRecord]:
        return [
            record
            for record in self._records
            if record.record_type == ProviderRecordType.product_offer
        ]

    async def fetch_offers(self) -> list[ProviderRawRecord]:
        return await self.fetch_products()

    async def fetch_prices(self) -> list[ProviderRawRecord]:
        return await self.fetch_products()

    async def fetch_coupons(self) -> list[ProviderRawRecord]:
        return [
            record for record in self._records if record.record_type == ProviderRecordType.coupon
        ]

    async def fetch_cashback(self) -> list[ProviderRawRecord]:
        return [
            record for record in self._records if record.record_type == ProviderRecordType.cashback
        ]

    async def fetch_incremental_updates(self) -> list[ProviderRawRecord]:
        return self._records

    def validate_record(self, record: ProviderRawRecord) -> ProviderValidationResult:
        payload = record.payload
        if payload.get("malformed"):
            return ProviderValidationResult(
                is_valid=False,
                error_code="malformed_record",
                message="Mock malformed provider record is missing required commercial fields.",
            )
        required = ["merchant_slug", "currency", "market"]
        if record.record_type == ProviderRecordType.product_offer:
            required.extend(["title", "provider_product_id", "price_cents", "affiliate_url"])
        if record.record_type == ProviderRecordType.coupon:
            required.extend(["code", "discount_type", "discount_value"])
        if record.record_type == ProviderRecordType.cashback:
            required.extend(["rate_type", "rate_value_bps"])
        missing = [field for field in required if field not in payload]
        if missing:
            return ProviderValidationResult(
                is_valid=False,
                error_code="missing_required_field",
                message=f"Missing required fields: {', '.join(missing)}",
            )
        return ProviderValidationResult(is_valid=True)

    def normalize_record(self, record: ProviderRawRecord) -> NormalizedRecord:
        payload = record.payload
        merchant = self._merchant_by_slug[str(payload["merchant_slug"])]
        if record.record_type == ProviderRecordType.coupon:
            return NormalizedCoupon(
                source_record_id=record.source_record_id,
                source_timestamp=record.source_timestamp,
                merchant=merchant,
                code=str(payload["code"]),
                description=str(payload["description"]),
                discount_type=str(payload["discount_type"]),
                discount_value=int(payload["discount_value"]),
                currency=str(payload["currency"]),
                market=str(payload["market"]),
                starts_at=payload.get("starts_at"),
                expires_at=payload.get("expires_at"),
            )
        if record.record_type == ProviderRecordType.cashback:
            return NormalizedCashbackOffer(
                source_record_id=record.source_record_id,
                source_timestamp=record.source_timestamp,
                merchant=merchant,
                rate_type=str(payload["rate_type"]),
                rate_value_bps=int(payload["rate_value_bps"]),
                currency=str(payload["currency"]),
                market=str(payload["market"]),
                starts_at=payload.get("starts_at"),
                expires_at=payload.get("expires_at"),
            )
        return NormalizedProductOffer(
            source_record_id=record.source_record_id,
            provider_product_id=str(payload["provider_product_id"]),
            source_timestamp=record.source_timestamp,
            merchant=merchant,
            brand_name=str(payload["brand_name"]),
            category_name=str(payload["category_name"]),
            category_slug=str(payload["category_slug"]),
            title=str(payload["title"]),
            description=payload.get("description"),
            mpn=payload.get("mpn"),
            merchant_sku=payload.get("merchant_sku"),
            identifiers=[
                NormalizedIdentifier(identifier_type=item["type"], identifier_value=item["value"])
                for item in payload.get("identifiers", [])
            ],
            price_cents=int(payload["price_cents"]),
            sale_price_cents=payload.get("sale_price_cents"),
            currency=str(payload["currency"]),
            market=str(payload["market"]),
            product_url=payload.get("product_url"),
            affiliate_url=str(payload["affiliate_url"]),
            availability=str(payload.get("availability", "in_stock")),
            provider_metadata={"fixture": True},
        )

    def _record(
        self,
        source_record_id: str,
        record_type: ProviderRecordType,
        source_timestamp: str,
        payload: dict[str, Any],
    ) -> ProviderRawRecord:
        return ProviderRawRecord(
            source_record_id=source_record_id,
            record_type=record_type,
            source_timestamp=dt(source_timestamp),
            payload=payload,
        )

    def _product(
        self,
        source_record_id: str,
        source_timestamp: str,
        merchant_slug: str,
        provider_product_id: str,
        title: str,
        brand_name: str,
        category_name: str,
        category_slug: str,
        price_cents: int,
        affiliate_url: str,
        *,
        sale_price_cents: int | None = None,
        mpn: str | None = None,
        merchant_sku: str | None = None,
        identifiers: list[dict[str, str]] | None = None,
    ) -> ProviderRawRecord:
        return self._record(
            source_record_id,
            ProviderRecordType.product_offer,
            source_timestamp,
            {
                "merchant_slug": merchant_slug,
                "provider_product_id": provider_product_id,
                "title": title,
                "brand_name": brand_name,
                "category_name": category_name,
                "category_slug": category_slug,
                "mpn": mpn,
                "merchant_sku": merchant_sku,
                "identifiers": identifiers or [],
                "price_cents": price_cents,
                "sale_price_cents": sale_price_cents,
                "currency": self.currency,
                "market": self.market,
                "product_url": f"https://{merchant_slug}.example.test/products/{provider_product_id}",
                "affiliate_url": affiliate_url,
                "availability": "in_stock",
            },
        )

    def _build_records(self) -> list[ProviderRawRecord]:
        records = [
            self._product(
                "mt-wavebuds-offer",
                "2026-07-09T10:00:00",
                "maple-tech",
                "MT-WAVEBUDS-BLACK",
                "Aurora WaveBuds Noise Cancelling Earbuds",
                "Aurora Audio",
                "Electronics",
                "electronics",
                12999,
                "https://affiliate.example.test/mt-wavebuds",
                sale_price_cents=9999,
                mpn="AWB-2026",
                merchant_sku="MT-88421",
                identifiers=[{"type": "upc", "value": "061414112345"}],
            ),
            self._product(
                "no-wavebuds-offer",
                "2026-07-09T10:05:00",
                "north-outfitters",
                "NO-AWB-2026",
                "Aurora WaveBuds ANC Earbuds",
                "Aurora Audio",
                "Electronics",
                "electronics",
                12499,
                "https://affiliate.example.test/no-wavebuds",
                sale_price_cents=10499,
                mpn="AWB-2026",
                merchant_sku="NO-9901",
                identifiers=[{"type": "gtin", "value": "00061414112345"}],
            ),
            self._product(
                "mt-kettle-offer",
                "2026-07-09T11:00:00",
                "maple-tech",
                "MT-KETTLE-1L",
                "Summit Home Smart Kettle 1L",
                "Summit Home",
                "Home",
                "home",
                8999,
                "https://affiliate.example.test/mt-kettle",
                mpn="SHK-1L-CA",
                merchant_sku="MT-7731",
                identifiers=[{"type": "ean", "value": "0701234567890"}],
            ),
            self._product(
                "bn-python-book-offer",
                "2026-07-09T12:00:00",
                "book-nook-canada",
                "BN-PY-DATA",
                "Practical Python Data Tools",
                "Northstar Press",
                "Books",
                "books",
                4599,
                "https://affiliate.example.test/bn-python",
                sale_price_cents=3999,
                mpn="NSP-PYDATA",
                merchant_sku="BN-10001",
                identifiers=[{"type": "isbn", "value": "9781999999991"}],
            ),
            self._product(
                "no-pack-offer",
                "2026-07-09T13:00:00",
                "north-outfitters",
                "NO-TRAILPACK-32",
                "Boreal Trail Pack 32L",
                "Boreal Gear",
                "Outdoor",
                "outdoor",
                14999,
                "https://affiliate.example.test/no-pack",
                sale_price_cents=11999,
                mpn="BTP-32",
                merchant_sku="NO-3210",
                identifiers=[{"type": "mpn", "value": "BTP-32"}],
            ),
            self._product(
                "mt-monitor-offer",
                "2026-07-09T14:00:00",
                "maple-tech",
                "MT-VIEW27",
                "LumaView 27 inch 4K Monitor",
                "LumaView",
                "Electronics",
                "electronics",
                39999,
                "https://affiliate.example.test/mt-monitor",
                sale_price_cents=34999,
                mpn="LV-27-4K",
                merchant_sku="MT-2727",
                identifiers=[{"type": "provider_product_id", "value": "MT-VIEW27"}],
            ),
        ]
        records.append(records[0].model_copy(deep=True))
        records.append(
            self._record(
                "malformed-record",
                ProviderRecordType.product_offer,
                "2026-07-09T15:00:00",
                {"malformed": True, "merchant_slug": "maple-tech", "currency": self.currency},
            )
        )
        records.append(
            self._product(
                "stale-pack-offer",
                "2026-05-01T10:00:00",
                "north-outfitters",
                "NO-TRAILPACK-32-OLD",
                "Boreal Trail Pack 32L Old Feed",
                "Boreal Gear",
                "Outdoor",
                "outdoor",
                15999,
                "https://affiliate.example.test/no-pack-old",
                mpn="BTP-32",
                merchant_sku="NO-3210-OLD",
                identifiers=[{"type": "mpn", "value": "BTP-32"}],
            )
        )
        records.extend(
            [
                self._record(
                    "coupon-maple-summer",
                    ProviderRecordType.coupon,
                    "2026-07-09T16:00:00",
                    {
                        "merchant_slug": "maple-tech",
                        "code": "MAPLE10",
                        "description": "10 CAD off electronics over 100 CAD",
                        "discount_type": "fixed_cents",
                        "discount_value": 1000,
                        "currency": self.currency,
                        "market": self.market,
                        "starts_at": dt("2026-07-01T00:00:00"),
                        "expires_at": dt("2026-08-31T23:59:59"),
                    },
                ),
                self._record(
                    "coupon-book-expired",
                    ProviderRecordType.coupon,
                    "2026-07-09T16:05:00",
                    {
                        "merchant_slug": "book-nook-canada",
                        "code": "SPRING5",
                        "description": "Expired spring book coupon",
                        "discount_type": "percent",
                        "discount_value": 5,
                        "currency": self.currency,
                        "market": self.market,
                        "starts_at": dt("2026-04-01T00:00:00"),
                        "expires_at": dt("2026-05-01T00:00:00"),
                    },
                ),
                self._record(
                    "cashback-north",
                    ProviderRecordType.cashback,
                    "2026-07-09T16:10:00",
                    {
                        "merchant_slug": "north-outfitters",
                        "rate_type": "percent_bps",
                        "rate_value_bps": 250,
                        "currency": self.currency,
                        "market": self.market,
                        "starts_at": dt("2026-07-01T00:00:00"),
                        "expires_at": dt("2026-09-01T00:00:00"),
                    },
                ),
            ]
        )
        return records
