from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.search import SearchFilters, search_offers, valid_freshness

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


class SearchResponse(BaseModel):
    query: str | None
    count: int
    results: list[SearchResult] = Field(default_factory=list)


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
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResponse:
    try:
        freshness_filter = valid_freshness(freshness)
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
            limit=limit,
        ),
    )
    search_results = [SearchResult(**result) for result in results]
    return SearchResponse(query=q, count=len(search_results), results=search_results)
