from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models import (
    AffiliateClickEvent,
    AffiliateSyncError,
    AffiliateSyncJob,
    CanonicalProduct,
    CashbackOffer,
    Coupon,
    MerchantListing,
    Offer,
    PriceHistory,
)
from app.services.affiliate.ingestion import AffiliateIngestionService
from app.services.affiliate.registry import registry

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(
    prefix="/admin/affiliate",
    tags=["admin-affiliate"],
    dependencies=[Depends(require_admin)],
)


class SyncStatsResponse(BaseModel):
    received: int
    inserted: int
    updated: int
    skipped: int
    rejected: int
    duplicate: int
    stale: int
    errors: int


class SyncResultResponse(BaseModel):
    job_id: int
    provider_source: str
    status: str
    stats: SyncStatsResponse


def row(model: Any, *fields: str) -> dict[str, Any]:
    return {field: getattr(model, field) for field in fields}


@router.post("/sync/mock", response_model=SyncResultResponse)
async def run_mock_sync(db: DbSession) -> SyncResultResponse:
    provider = registry.get("mock_ca")
    result = await AffiliateIngestionService(db, provider).run_sync()
    return SyncResultResponse(
        job_id=result.job_id,
        provider_source=result.provider_source,
        status=result.status,
        stats=SyncStatsResponse(**result.stats.__dict__),
    )


@router.get("/sync/jobs")
def list_sync_jobs(db: DbSession) -> list[dict[str, Any]]:
    jobs = db.scalars(select(AffiliateSyncJob).order_by(AffiliateSyncJob.id.desc())).all()
    return [
        row(
            job,
            "id",
            "status",
            "started_at",
            "completed_at",
            "received_count",
            "inserted_count",
            "updated_count",
            "skipped_count",
            "rejected_count",
            "duplicate_count",
            "stale_count",
            "error_count",
        )
        for job in jobs
    ]


@router.get("/sync/errors")
def list_sync_errors(db: DbSession) -> list[dict[str, Any]]:
    errors = db.scalars(select(AffiliateSyncError).order_by(AffiliateSyncError.id.desc())).all()
    return [
        row(error, "id", "sync_job_id", "source_record_id", "error_code", "message")
        for error in errors
    ]


@router.get("/products")
def list_canonical_products(db: DbSession) -> list[dict[str, Any]]:
    products = db.scalars(select(CanonicalProduct).order_by(CanonicalProduct.id)).all()
    return [
        {
            "id": product.id,
            "title": product.title,
            "brand": product.brand.name if product.brand else None,
            "category": product.category.name if product.category else None,
            "mpn": product.mpn,
            "resolution_status": product.resolution_status,
        }
        for product in products
    ]


@router.get("/listings")
def list_product_listings(db: DbSession) -> list[dict[str, Any]]:
    listings = db.scalars(select(MerchantListing).order_by(MerchantListing.id)).all()
    return [
        {
            "id": listing.id,
            "canonical_product_id": listing.canonical_product_id,
            "merchant": listing.merchant.name,
            "title": listing.title,
            "provider_source": listing.provider_source,
            "provider_product_id": listing.provider_product_id,
            "freshness_status": listing.freshness_status,
            "record_status": listing.record_status,
        }
        for listing in listings
    ]


@router.get("/offers")
def list_offers(db: DbSession) -> list[dict[str, Any]]:
    offers = db.scalars(select(Offer).order_by(Offer.id)).all()
    return [
        row(
            offer,
            "id",
            "merchant_listing_id",
            "title",
            "price_cents",
            "sale_price_cents",
            "currency",
            "market",
            "freshness_status",
            "record_status",
        )
        for offer in offers
    ]


@router.get("/price-history")
def list_price_history(db: DbSession) -> list[dict[str, Any]]:
    prices = db.scalars(select(PriceHistory).order_by(PriceHistory.id)).all()
    return [
        row(
            price,
            "id",
            "merchant_listing_id",
            "observed_at",
            "price_cents",
            "sale_price_cents",
            "currency",
            "market",
        )
        for price in prices
    ]


@router.get("/coupons")
def list_coupons(db: DbSession) -> list[dict[str, Any]]:
    coupons = db.scalars(select(Coupon).order_by(Coupon.id)).all()
    return [
        row(
            coupon,
            "id",
            "merchant_id",
            "code",
            "description",
            "discount_type",
            "discount_value",
            "currency",
            "market",
            "expires_at",
            "is_expired",
        )
        for coupon in coupons
    ]


@router.get("/cashback")
def list_cashback(db: DbSession) -> list[dict[str, Any]]:
    offers = db.scalars(select(CashbackOffer).order_by(CashbackOffer.id)).all()
    return [
        row(
            offer,
            "id",
            "merchant_id",
            "rate_type",
            "rate_value_bps",
            "currency",
            "market",
            "expires_at",
            "record_status",
        )
        for offer in offers
    ]


@router.get("/clicks")
def list_click_events(db: DbSession) -> list[dict[str, Any]]:
    events = db.scalars(
        select(AffiliateClickEvent).order_by(AffiliateClickEvent.id.desc()).limit(50)
    ).all()
    return [
        {
            "id": event.id,
            "offer_id": event.offer_id,
            "merchant_id": event.merchant_id,
            "merchant_listing_id": event.merchant_listing_id,
            "merchant": event.merchant.name if event.merchant else None,
            "offer_title": event.offer.title if event.offer else None,
            "target_type": event.target_type,
            "target_url": event.target_url,
            "provider_source": event.provider_source,
            "source_record_id": event.source_record_id,
            "market": event.market,
            "referrer": event.referrer,
            "created_at": event.created_at,
        }
        for event in events
    ]
