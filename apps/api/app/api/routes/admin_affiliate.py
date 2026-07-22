from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
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


class StagingCountsResponse(BaseModel):
    products: int
    listings: int
    offers: int
    coupons: int
    cashback_offers: int
    click_events: int
    sync_jobs: int
    sync_errors: int


class StagingSyncJobResponse(BaseModel):
    id: int
    provider_source: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    received_count: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    rejected_count: int
    duplicate_count: int
    stale_count: int
    error_count: int


class StagingSyncErrorResponse(BaseModel):
    id: int
    sync_job_id: int
    source_record_id: str | None
    error_code: str
    message: str


class StagingSummaryResponse(BaseModel):
    counts: StagingCountsResponse
    latest_sync_job: StagingSyncJobResponse | None
    recent_errors: list[StagingSyncErrorResponse]


def row(model: Any, *fields: str) -> dict[str, Any]:
    return {field: getattr(model, field) for field in fields}


def _click_target_counts(events: Sequence[AffiliateClickEvent]) -> dict[str, int]:
    counts = {"product": 0, "affiliate": 0}
    for event in events:
        counts[event.target_type] = counts.get(event.target_type, 0) + 1
    return counts


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


@router.get("/staging-summary", response_model=StagingSummaryResponse)
def get_staging_summary(db: DbSession) -> StagingSummaryResponse:
    latest_job = db.scalars(
        select(AffiliateSyncJob).order_by(AffiliateSyncJob.id.desc()).limit(1)
    ).first()
    recent_errors = db.scalars(
        select(AffiliateSyncError).order_by(AffiliateSyncError.id.desc()).limit(5)
    ).all()

    return StagingSummaryResponse(
        counts=StagingCountsResponse(
            products=db.scalar(select(func.count(CanonicalProduct.id))) or 0,
            listings=db.scalar(select(func.count(MerchantListing.id))) or 0,
            offers=db.scalar(select(func.count(Offer.id))) or 0,
            coupons=db.scalar(select(func.count(Coupon.id))) or 0,
            cashback_offers=db.scalar(select(func.count(CashbackOffer.id))) or 0,
            click_events=db.scalar(select(func.count(AffiliateClickEvent.id))) or 0,
            sync_jobs=db.scalar(select(func.count(AffiliateSyncJob.id))) or 0,
            sync_errors=db.scalar(select(func.count(AffiliateSyncError.id))) or 0,
        ),
        latest_sync_job=(
            StagingSyncJobResponse(
                id=latest_job.id,
                provider_source=latest_job.provider.source if latest_job.provider else None,
                status=latest_job.status,
                started_at=latest_job.started_at,
                completed_at=latest_job.completed_at,
                received_count=latest_job.received_count,
                inserted_count=latest_job.inserted_count,
                updated_count=latest_job.updated_count,
                skipped_count=latest_job.skipped_count,
                rejected_count=latest_job.rejected_count,
                duplicate_count=latest_job.duplicate_count,
                stale_count=latest_job.stale_count,
                error_count=latest_job.error_count,
            )
            if latest_job
            else None
        ),
        recent_errors=[
            StagingSyncErrorResponse(
                id=error.id,
                sync_job_id=error.sync_job_id,
                source_record_id=error.source_record_id,
                error_code=error.error_code,
                message=error.message,
            )
            for error in recent_errors
        ],
    )


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


@router.get("/click-analytics")
def get_click_analytics(db: DbSession) -> dict[str, Any]:
    total_clicks = db.scalar(select(func.count(AffiliateClickEvent.id))) or 0
    recent_events = db.scalars(
        select(AffiliateClickEvent).order_by(AffiliateClickEvent.id.desc()).limit(20)
    ).all()
    target_counts = _click_target_counts(db.scalars(select(AffiliateClickEvent)).all())
    offer_rows = db.execute(
        select(
            AffiliateClickEvent.offer_id,
            Offer.title,
            AffiliateClickEvent.provider_source,
            AffiliateClickEvent.market,
            func.count(AffiliateClickEvent.id).label("click_count"),
        )
        .outerjoin(Offer, AffiliateClickEvent.offer_id == Offer.id)
        .group_by(
            AffiliateClickEvent.offer_id,
            Offer.title,
            AffiliateClickEvent.provider_source,
            AffiliateClickEvent.market,
        )
        .order_by(func.count(AffiliateClickEvent.id).desc(), AffiliateClickEvent.offer_id)
        .limit(10)
    ).all()
    merchant_rows = db.execute(
        select(
            AffiliateClickEvent.merchant_id,
            AffiliateClickEvent.provider_source,
            func.count(AffiliateClickEvent.id).label("click_count"),
        )
        .group_by(AffiliateClickEvent.merchant_id, AffiliateClickEvent.provider_source)
        .order_by(func.count(AffiliateClickEvent.id).desc(), AffiliateClickEvent.merchant_id)
        .limit(10)
    ).all()
    merchants_by_id = {
        listing.merchant_id: listing.merchant.name
        for listing in db.scalars(select(MerchantListing)).all()
    }

    return {
        "total_clicks": total_clicks,
        "target_counts": target_counts,
        "top_offers": [
            {
                "offer_id": offer_id,
                "offer_title": title,
                "provider_source": provider_source,
                "market": market,
                "click_count": click_count,
            }
            for offer_id, title, provider_source, market, click_count in offer_rows
        ],
        "top_merchants": [
            {
                "merchant_id": merchant_id,
                "merchant": merchants_by_id.get(merchant_id),
                "provider_source": provider_source,
                "click_count": click_count,
            }
            for merchant_id, provider_source, click_count in merchant_rows
        ],
        "recent_clicks": [
            {
                "id": event.id,
                "offer_id": event.offer_id,
                "merchant": event.merchant.name if event.merchant else None,
                "target_type": event.target_type,
                "provider_source": event.provider_source,
                "market": event.market,
                "created_at": event.created_at,
            }
            for event in recent_events
        ],
    }
