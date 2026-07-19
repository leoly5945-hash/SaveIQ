from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AffiliateLink,
    AffiliateProvider,
    AffiliateSyncError,
    AffiliateSyncJob,
    Brand,
    CanonicalProduct,
    CashbackOffer,
    Category,
    Coupon,
    Merchant,
    MerchantListing,
    Offer,
    PriceHistory,
    ProductIdentifier,
    RawProviderRecord,
)
from app.models.affiliate import (
    FreshnessStatus,
    IdentifierType,
    RawRecordStatus,
    RecordStatus,
    SyncJobStatus,
)
from app.services.affiliate.schemas import (
    AffiliateProviderAdapter,
    NormalizedCashbackOffer,
    NormalizedCoupon,
    NormalizedIdentifier,
    NormalizedProductOffer,
    NormalizedRecord,
    ProviderRawRecord,
)

GLOBAL_IDENTIFIER_TYPES = {
    IdentifierType.gtin.value,
    IdentifierType.upc.value,
    IdentifierType.ean.value,
    IdentifierType.isbn.value,
}


@dataclass
class SyncStats:
    received: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    rejected: int = 0
    duplicate: int = 0
    stale: int = 0
    errors: int = 0


@dataclass
class SyncResult:
    job_id: int
    provider_source: str
    status: str
    stats: SyncStats


class CriticalSyncFailure(RuntimeError):
    pass


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def raw_record_hash(record: ProviderRawRecord) -> str:
    payload = record.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class AffiliateIngestionService:
    def __init__(self, session: Session, provider: AffiliateProviderAdapter) -> None:
        self.session = session
        self.provider = provider

    async def run_sync(self, *, simulate_critical_failure: bool = False) -> SyncResult:
        started_at = datetime.now(UTC)
        records = await self.provider.fetch_incremental_updates()
        stats = SyncStats(received=len(records))

        with self.session.begin():
            provider_model = self._get_or_create_provider()
            job = AffiliateSyncJob(
                provider=provider_model,
                status=SyncJobStatus.running.value,
                started_at=started_at,
                received_count=stats.received,
            )
            self.session.add(job)
            self.session.flush()

            for index, record in enumerate(records):
                try:
                    with self.session.begin_nested():
                        raw = self._store_raw_record(provider_model, job, record)
                        if simulate_critical_failure and index == 0:
                            raise CriticalSyncFailure("Simulated critical rollback")
                        if raw.status == RawRecordStatus.duplicate.value:
                            stats.duplicate += 1
                            stats.skipped += 1
                            continue
                        if self._is_stale(record):
                            raw.status = RawRecordStatus.stale.value
                            stats.stale += 1
                            stats.skipped += 1
                            continue
                        validation = self.provider.validate_record(record)
                        if not validation.is_valid:
                            raw.status = RawRecordStatus.rejected.value
                            raw.error_message = validation.message
                            self._record_error(
                                job,
                                record.source_record_id,
                                validation.error_code or "validation_failed",
                                validation.message or "Provider record failed validation.",
                            )
                            stats.rejected += 1
                            continue

                        normalized = self.provider.normalize_record(record)
                        raw.status = RawRecordStatus.normalized.value
                        result = self._upsert_normalized(normalized)
                        stats.inserted += result["inserted"]
                        stats.updated += result["updated"]
                except CriticalSyncFailure:
                    raise
                except Exception as exc:  # noqa: BLE001 - errors must be auditable per record.
                    stats.errors += 1
                    self._record_error(job, record.source_record_id, "processing_error", str(exc))

            job.status = (
                SyncJobStatus.completed_with_errors.value
                if stats.errors or stats.rejected
                else SyncJobStatus.completed.value
            )
            job.completed_at = datetime.now(UTC)
            job.inserted_count = stats.inserted
            job.updated_count = stats.updated
            job.skipped_count = stats.skipped
            job.rejected_count = stats.rejected
            job.duplicate_count = stats.duplicate
            job.stale_count = stats.stale
            job.error_count = stats.errors

        return SyncResult(
            job_id=job.id,
            provider_source=self.provider.source,
            status=job.status,
            stats=stats,
        )

    def _get_or_create_provider(self) -> AffiliateProvider:
        provider = self.session.scalar(
            select(AffiliateProvider).where(AffiliateProvider.source == self.provider.source)
        )
        if provider:
            provider.name = self.provider.name
            provider.market = self.provider.market
            provider.currency = self.provider.currency
            return provider
        provider = AffiliateProvider(
            source=self.provider.source,
            name=self.provider.name,
            market=self.provider.market,
            currency=self.provider.currency,
        )
        self.session.add(provider)
        self.session.flush()
        return provider

    def _store_raw_record(
        self,
        provider: AffiliateProvider,
        job: AffiliateSyncJob,
        record: ProviderRawRecord,
    ) -> RawProviderRecord:
        digest = raw_record_hash(record)
        existing = self.session.scalar(
            select(RawProviderRecord).where(
                RawProviderRecord.provider_id == provider.id,
                RawProviderRecord.source_record_id == record.source_record_id,
                RawProviderRecord.record_hash == digest,
            )
        )
        if existing:
            duplicate = RawProviderRecord(
                provider=provider,
                sync_job=job,
                source_record_id=record.source_record_id,
                record_type=record.record_type.value,
                record_hash=f"{digest[:48]}:{job.id}:{datetime.now(UTC).timestamp()}",
                source_timestamp=record.source_timestamp,
                ingested_at=datetime.now(UTC),
                status=RawRecordStatus.duplicate.value,
                raw_payload=self._safe_payload(record),
            )
            self.session.add(duplicate)
            self.session.flush()
            return duplicate

        raw = RawProviderRecord(
            provider=provider,
            sync_job=job,
            source_record_id=record.source_record_id,
            record_type=record.record_type.value,
            record_hash=digest,
            source_timestamp=record.source_timestamp,
            ingested_at=datetime.now(UTC),
            status=RawRecordStatus.received.value,
            raw_payload=self._safe_payload(record),
        )
        self.session.add(raw)
        self.session.flush()
        return raw

    def _safe_payload(self, record: ProviderRawRecord) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        payload["payload"].pop("affiliate_url", None)
        return payload

    def _is_stale(self, record: ProviderRawRecord) -> bool:
        return record.source_timestamp < datetime.now(UTC) - timedelta(days=30)

    def _record_error(
        self,
        job: AffiliateSyncJob,
        source_record_id: str | None,
        error_code: str,
        message: str,
    ) -> None:
        self.session.add(
            AffiliateSyncError(
                sync_job=job,
                source_record_id=source_record_id,
                error_code=error_code,
                message=message[:500],
            )
        )

    def _upsert_normalized(self, record: NormalizedRecord) -> dict[str, int]:
        if isinstance(record, NormalizedProductOffer):
            return self._upsert_product_offer(record)
        if isinstance(record, NormalizedCoupon):
            return self._upsert_coupon(record)
        if isinstance(record, NormalizedCashbackOffer):
            return self._upsert_cashback(record)
        raise TypeError(f"Unsupported normalized record: {type(record).__name__}")

    def _upsert_product_offer(self, record: NormalizedProductOffer) -> dict[str, int]:
        inserted = 0
        updated = 0
        merchant, merchant_inserted = self._get_or_create_merchant(record)
        brand, brand_inserted = self._get_or_create_brand(record.brand_name)
        category, category_inserted = self._get_or_create_category(
            record.category_name,
            record.category_slug,
        )
        product, product_inserted = self._resolve_product(record, brand, category)
        listing, listing_inserted = self._upsert_listing(record, product, merchant)
        link, link_inserted = self._upsert_affiliate_link(record, merchant)
        _, offer_inserted = self._upsert_offer(record, listing, link)
        price_inserted = self._append_price_history(record, listing)
        inserted += sum(
            [
                merchant_inserted,
                brand_inserted,
                category_inserted,
                product_inserted,
                listing_inserted,
                link_inserted,
                offer_inserted,
                price_inserted,
            ]
        )
        if not listing_inserted or not offer_inserted:
            updated += 1
        return {"inserted": inserted, "updated": updated}

    def _get_or_create_merchant(
        self,
        record: NormalizedProductOffer | NormalizedCoupon | NormalizedCashbackOffer,
    ) -> tuple[Merchant, int]:
        merchant = self.session.scalar(
            select(Merchant).where(Merchant.slug == record.merchant.slug)
        )
        if merchant:
            merchant.name = record.merchant.name
            merchant.market = record.merchant.market
            merchant.website_url = (
                str(record.merchant.website_url) if record.merchant.website_url else None
            )
            return merchant, 0
        merchant = Merchant(
            name=record.merchant.name,
            slug=record.merchant.slug,
            market=record.merchant.market,
            website_url=str(record.merchant.website_url) if record.merchant.website_url else None,
        )
        self.session.add(merchant)
        self.session.flush()
        return merchant, 1

    def _get_or_create_brand(self, brand_name: str) -> tuple[Brand, int]:
        normalized = normalize_text(brand_name)
        brand = self.session.scalar(select(Brand).where(Brand.normalized_name == normalized))
        if brand:
            return brand, 0
        brand = Brand(name=brand_name, normalized_name=normalized)
        self.session.add(brand)
        self.session.flush()
        return brand, 1

    def _get_or_create_category(self, name: str, slug: str) -> tuple[Category, int]:
        category = self.session.scalar(select(Category).where(Category.slug == slug))
        if category:
            return category, 0
        category = Category(name=name, slug=slug)
        self.session.add(category)
        self.session.flush()
        return category, 1

    def _resolve_product(
        self,
        record: NormalizedProductOffer,
        brand: Brand,
        category: Category,
    ) -> tuple[CanonicalProduct, int]:
        global_identifier = next(
            (
                identifier
                for identifier in record.identifiers
                if identifier.identifier_type in GLOBAL_IDENTIFIER_TYPES
            ),
            None,
        )
        if global_identifier:
            product = self._find_product_by_identifier(global_identifier)
            if product:
                return product, 0

        if record.mpn:
            product = self.session.scalar(
                select(CanonicalProduct).where(
                    CanonicalProduct.brand_id == brand.id,
                    CanonicalProduct.mpn == record.mpn,
                )
            )
            if product:
                self._ensure_identifier(product, "mpn", record.mpn, None)
                return product, 0

        provider_identifier = NormalizedIdentifier(
            identifier_type=IdentifierType.provider_product_id.value,
            identifier_value=record.provider_product_id,
        )
        product = self._find_product_by_identifier(provider_identifier, self.provider.source)
        if product:
            return product, 0

        has_deterministic_match = bool(global_identifier or record.mpn)
        product = CanonicalProduct(
            title=record.title,
            brand=brand,
            category=category,
            mpn=record.mpn,
            resolution_status="resolved" if has_deterministic_match else "unresolved_review",
            review_reason=None if has_deterministic_match else "No deterministic identifier match.",
        )
        self.session.add(product)
        self.session.flush()
        for identifier in record.identifiers:
            self._ensure_identifier(
                product,
                identifier.identifier_type,
                identifier.identifier_value,
                None,
            )
        if record.mpn:
            self._ensure_identifier(product, IdentifierType.mpn.value, record.mpn, None)
        self._ensure_identifier(
            product,
            IdentifierType.provider_product_id.value,
            record.provider_product_id,
            self.provider.source,
        )
        return product, 1

    def _find_product_by_identifier(
        self,
        identifier: NormalizedIdentifier,
        provider_source: str | None = None,
    ) -> CanonicalProduct | None:
        query = select(ProductIdentifier).where(
            ProductIdentifier.identifier_type == identifier.identifier_type,
            ProductIdentifier.identifier_value == identifier.identifier_value,
        )
        if provider_source:
            query = query.where(ProductIdentifier.provider_source == provider_source)
        found = self.session.scalar(query)
        return found.product if found else None

    def _ensure_identifier(
        self,
        product: CanonicalProduct,
        identifier_type: str,
        identifier_value: str,
        provider_source: str | None,
    ) -> None:
        existing = self.session.scalar(
            select(ProductIdentifier).where(
                ProductIdentifier.identifier_type == identifier_type,
                ProductIdentifier.identifier_value == identifier_value,
                ProductIdentifier.provider_source == provider_source,
            )
        )
        if existing:
            return
        self.session.add(
            ProductIdentifier(
                product=product,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
                provider_source=provider_source,
            )
        )

    def _source_fields(
        self,
        record: NormalizedProductOffer | NormalizedCoupon | NormalizedCashbackOffer,
    ) -> dict[str, Any]:
        return {
            "provider_source": self.provider.source,
            "source_record_id": record.source_record_id,
            "source_timestamp": record.source_timestamp,
            "last_successful_update": datetime.now(UTC),
            "freshness_status": FreshnessStatus.fresh.value,
            "currency": record.currency,
            "market": record.market,
            "record_status": RecordStatus.active.value,
        }

    def _upsert_listing(
        self,
        record: NormalizedProductOffer,
        product: CanonicalProduct,
        merchant: Merchant,
    ) -> tuple[MerchantListing, int]:
        listing = self.session.scalar(
            select(MerchantListing).where(
                MerchantListing.provider_source == self.provider.source,
                MerchantListing.provider_product_id == record.provider_product_id,
                MerchantListing.merchant_id == merchant.id,
            )
        )
        fields = self._source_fields(record)
        if listing:
            listing.title = record.title
            listing.canonical_product = product
            listing.merchant_sku = record.merchant_sku
            listing.product_url = str(record.product_url) if record.product_url else None
            listing.provider_metadata = record.provider_metadata
            for key, value in fields.items():
                setattr(listing, key, value)
            return listing, 0
        listing = MerchantListing(
            canonical_product=product,
            merchant=merchant,
            title=record.title,
            merchant_sku=record.merchant_sku,
            provider_product_id=record.provider_product_id,
            product_url=str(record.product_url) if record.product_url else None,
            provider_metadata=record.provider_metadata,
            **fields,
        )
        self.session.add(listing)
        self.session.flush()
        self._ensure_identifier(
            product,
            IdentifierType.merchant_sku.value,
            record.merchant_sku or record.provider_product_id,
            self.provider.source,
        )
        return listing, 1

    def _upsert_affiliate_link(
        self,
        record: NormalizedProductOffer,
        merchant: Merchant,
    ) -> tuple[AffiliateLink, int]:
        link = self.session.scalar(
            select(AffiliateLink).where(
                AffiliateLink.provider_source == self.provider.source,
                AffiliateLink.source_record_id == f"{record.source_record_id}:link",
            )
        )
        fields = self._source_fields(record)
        fields["source_record_id"] = f"{record.source_record_id}:link"
        if link:
            link.url = str(record.affiliate_url)
            for key, value in fields.items():
                setattr(link, key, value)
            return link, 0
        link = AffiliateLink(merchant_id=merchant.id, url=str(record.affiliate_url), **fields)
        self.session.add(link)
        self.session.flush()
        return link, 1

    def _upsert_offer(
        self,
        record: NormalizedProductOffer,
        listing: MerchantListing,
        link: AffiliateLink,
    ) -> tuple[Offer, int]:
        offer = self.session.scalar(
            select(Offer).where(
                Offer.provider_source == self.provider.source,
                Offer.source_record_id == record.source_record_id,
            )
        )
        fields = self._source_fields(record)
        if offer:
            offer.title = record.title
            offer.price_cents = record.price_cents
            offer.sale_price_cents = record.sale_price_cents
            offer.availability = record.availability
            offer.affiliate_link = link
            for key, value in fields.items():
                setattr(offer, key, value)
            return offer, 0
        offer = Offer(
            listing=listing,
            title=record.title,
            price_cents=record.price_cents,
            sale_price_cents=record.sale_price_cents,
            availability=record.availability,
            affiliate_link=link,
            **fields,
        )
        self.session.add(offer)
        self.session.flush()
        return offer, 1

    def _append_price_history(
        self,
        record: NormalizedProductOffer,
        listing: MerchantListing,
    ) -> int:
        existing = self.session.scalar(
            select(PriceHistory).where(
                PriceHistory.merchant_listing_id == listing.id,
                PriceHistory.observed_at == record.source_timestamp,
                PriceHistory.price_cents == record.price_cents,
                PriceHistory.sale_price_cents == record.sale_price_cents,
            )
        )
        if existing:
            return 0
        self.session.add(
            PriceHistory(
                listing=listing,
                observed_at=record.source_timestamp,
                price_cents=record.price_cents,
                sale_price_cents=record.sale_price_cents,
                **self._source_fields(record),
            )
        )
        return 1

    def _upsert_coupon(self, record: NormalizedCoupon) -> dict[str, int]:
        merchant, merchant_inserted = self._get_or_create_merchant(record)
        coupon = self.session.scalar(
            select(Coupon).where(
                Coupon.provider_source == self.provider.source,
                Coupon.source_record_id == record.source_record_id,
            )
        )
        fields = self._source_fields(record)
        is_expired = bool(record.expires_at and record.expires_at < datetime.now(UTC))
        if coupon:
            coupon.code = record.code
            coupon.description = record.description
            coupon.discount_type = record.discount_type
            coupon.discount_value = record.discount_value
            coupon.starts_at = record.starts_at
            coupon.expires_at = record.expires_at
            coupon.is_expired = is_expired
            for key, value in fields.items():
                setattr(coupon, key, value)
            return {"inserted": merchant_inserted, "updated": 1}
        self.session.add(
            Coupon(
                merchant_id=merchant.id,
                code=record.code,
                description=record.description,
                discount_type=record.discount_type,
                discount_value=record.discount_value,
                starts_at=record.starts_at,
                expires_at=record.expires_at,
                is_expired=is_expired,
                **fields,
            )
        )
        return {"inserted": merchant_inserted + 1, "updated": 0}

    def _upsert_cashback(self, record: NormalizedCashbackOffer) -> dict[str, int]:
        merchant, merchant_inserted = self._get_or_create_merchant(record)
        cashback = self.session.scalar(
            select(CashbackOffer).where(
                CashbackOffer.provider_source == self.provider.source,
                CashbackOffer.source_record_id == record.source_record_id,
            )
        )
        fields = self._source_fields(record)
        if cashback:
            cashback.rate_type = record.rate_type
            cashback.rate_value_bps = record.rate_value_bps
            cashback.starts_at = record.starts_at
            cashback.expires_at = record.expires_at
            for key, value in fields.items():
                setattr(cashback, key, value)
            return {"inserted": merchant_inserted, "updated": 1}
        self.session.add(
            CashbackOffer(
                merchant_id=merchant.id,
                rate_type=record.rate_type,
                rate_value_bps=record.rate_value_bps,
                starts_at=record.starts_at,
                expires_at=record.expires_at,
                **fields,
            )
        )
        return {"inserted": merchant_inserted + 1, "updated": 0}
