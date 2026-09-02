from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.featured_deals import (
    get_featured_deal,
    list_deal_categories,
    list_featured_deals,
)

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/featured-deals", tags=["featured-deals"])


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


@router.get("", response_model=FeaturedDealsResponse)
def get_featured_deals(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    category: Annotated[str | None, Query(max_length=80)] = None,
) -> FeaturedDealsResponse:
    deals = list_featured_deals(db, limit=limit, category_slug=category)
    return FeaturedDealsResponse(
        count=len(deals),
        deals=[FeaturedDealResponse(**deal) for deal in deals],
    )


@router.get("/categories", response_model=DealCategoriesResponse)
def get_deal_categories(db: DbSession) -> DealCategoriesResponse:
    categories = list_deal_categories(db)
    return DealCategoriesResponse(
        count=len(categories),
        categories=[DealCategoryResponse(**cat) for cat in categories],
    )


@router.get("/{slug}", response_model=FeaturedDealResponse)
def get_featured_deal_by_slug(
    db: DbSession,
    slug: Annotated[str, Path(max_length=200)],
) -> FeaturedDealResponse:
    deal = get_featured_deal(db, slug)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return FeaturedDealResponse(**deal)
