from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.search import (
    SearchFilters,
    get_offer_detail,
    search_offers,
    valid_freshness,
    valid_sort,
)

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    offer_id: int
    product_id: int
    title: str
    offer_title: str
    merchant: str
    brand: str | None
    category: str | None
    price_cents: int
    sale_price_cents: int | None
    currency: str
    market: str
    availability: str
    freshness_status: str
    provider_source: str
    product_url: str | None
    has_coupon: bool
    has_cashback: bool
    match_reasons: list[str]


class SearchResponse(BaseModel):
    query: str | None
    count: int
    results: list[SearchResult] = Field(default_factory=list)


class CouponSummary(BaseModel):
    code: str
    description: str
    discount_type: str
    discount_value: int
    expires_at: datetime | None


class CashbackSummary(BaseModel):
    rate_type: str
    rate_value_bps: int
    expires_at: datetime | None


class PricePoint(BaseModel):
    observed_at: datetime
    price_cents: int
    sale_price_cents: int | None


class SourceAttribution(BaseModel):
    provider_source: str
    source_record_id: str
    source_timestamp: datetime
    last_successful_update: datetime | None
    record_status: str


class OfferDetail(SearchResult):
    merchant_url: str | None
    affiliate_url: str | None
    source_attribution: SourceAttribution
    coupons: list[CouponSummary] = Field(default_factory=list)
    cashback_offers: list[CashbackSummary] = Field(default_factory=list)
    price_history: list[PricePoint] = Field(default_factory=list)


@router.get("", response_model=SearchResponse)
def search_products(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    merchant: Annotated[str | None, Query(max_length=120)] = None,
    brand: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
    has_coupon: bool | None = None,
    has_cashback: bool | None = None,
    freshness: Annotated[str | None, Query(max_length=40)] = None,
    sort: Annotated[str | None, Query(max_length=40)] = "price_asc",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResponse:
    try:
        freshness_filter = valid_freshness(freshness)
        sort_order = valid_sort(sort)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    results = search_offers(
        db,
        SearchFilters(
            query=q,
            merchant=merchant,
            brand=brand,
            category=category,
            has_coupon=has_coupon,
            has_cashback=has_cashback,
            freshness=freshness_filter,
            sort=sort_order,
            limit=limit,
        ),
    )
    search_results = [SearchResult(**result) for result in results]
    return SearchResponse(query=q, count=len(search_results), results=search_results)


@router.get("/offers/{offer_id}", response_model=OfferDetail)
def offer_detail(
    db: DbSession,
    offer_id: Annotated[int, Path(ge=1)],
) -> OfferDetail:
    result = get_offer_detail(db, offer_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return OfferDetail.model_validate(result)
