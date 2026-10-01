from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.session import get_db
from app.providers.amazon_creators import get_creators_client
from app.services.featured_deals import (
    get_featured_deal,
    list_deal_categories,
    list_featured_deals,
    list_price_drops,
)

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/featured-deals", tags=["featured-deals"])


class LatestPriceResponse(BaseModel):
    price_cents: int
    currency: str
    avg90_cents: int | None
    pct_below_avg90: int | None
    verdict: str | None = None
    observed_at: str


class FeaturedDealResponse(BaseModel):
    offer_id: int
    slug: str
    title: str
    brand: str | None
    category: str | None
    category_slug: str | None
    merchant: str
    price_cents: int
    currency: str
    product_url: str | None
    price_checked: str | None
    blurb: str | None
    latest_price: LatestPriceResponse | None = None
    no_offer_checked_at: str | None = None
    # Amazon's own product image (Creators API), when we hold one.
    image_url: str | None = None


class FeaturedDealsResponse(BaseModel):
    count: int
    deals: list[FeaturedDealResponse] = Field(default_factory=list)


class DealCategoryResponse(BaseModel):
    name: str
    slug: str
    count: int


class DealCategoriesResponse(BaseModel):
    count: int
    categories: list[DealCategoryResponse] = Field(default_factory=list)


_ASIN_IN_URL = re.compile(r"/dp/([A-Z0-9]{10})(?:[/?]|$)")


def _with_images(
    deals: Sequence[Mapping[str, Any]], background: BackgroundTasks
) -> list[FeaturedDealResponse]:
    """Attach the product images we already hold; fetch the rest after responding.

    A page never waits on Amazon: the first view of a product shows the category
    icon, and the image is there from the next view on.
    """

    client = get_creators_client(get_settings())
    asin_of: dict[int, str] = {}
    for deal in deals:
        match = _ASIN_IN_URL.search(str(deal.get("product_url") or ""))
        if match:
            asin_of[int(deal["offer_id"])] = match.group(1)
    images: dict[str, str] = {}
    if client is not None and asin_of:
        images = client.cached(asin_of.values())
        missing = client.missing(asin_of.values())
        if missing:
            background.add_task(client.warm, missing)
    return [
        FeaturedDealResponse(**deal, image_url=images.get(asin_of.get(int(deal["offer_id"]), "")))
        for deal in deals
    ]


@router.get("", response_model=FeaturedDealsResponse)
def get_featured_deals(
    db: DbSession,
    background: BackgroundTasks,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    category: Annotated[str | None, Query(max_length=80)] = None,
) -> FeaturedDealsResponse:
    deals = list_featured_deals(db, limit=limit, category_slug=category)
    return FeaturedDealsResponse(
        count=len(deals),
        deals=_with_images(deals, background),
    )


@router.get("/categories", response_model=DealCategoriesResponse)
def get_deal_categories(db: DbSession) -> DealCategoriesResponse:
    categories = list_deal_categories(db)
    return DealCategoriesResponse(
        count=len(categories),
        categories=[DealCategoryResponse(**cat) for cat in categories],
    )


@router.get("/price-drops", response_model=FeaturedDealsResponse)
def get_price_drops(
    db: DbSession,
    background: BackgroundTasks,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> FeaturedDealsResponse:
    """Price Watch products recorded under their 90-day average and near their
    90-day low today."""

    deals = list_price_drops(db, limit=limit)
    return FeaturedDealsResponse(
        count=len(deals),
        deals=_with_images(deals, background),
    )


@router.get("/{slug}", response_model=FeaturedDealResponse)
def get_featured_deal_by_slug(
    db: DbSession,
    background: BackgroundTasks,
    slug: Annotated[str, Path(max_length=200)],
) -> FeaturedDealResponse:
    deal = get_featured_deal(db, slug)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _with_images([deal], background)[0]
