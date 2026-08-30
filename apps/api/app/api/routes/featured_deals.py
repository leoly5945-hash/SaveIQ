from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.featured_deals import list_featured_deals

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/featured-deals", tags=["featured-deals"])


class FeaturedDealResponse(BaseModel):
    offer_id: int
    title: str
    brand: str | None
    category: str | None
    merchant: str
    price_cents: int
    currency: str
    product_url: str | None
    price_checked: str | None
    blurb: str | None


class FeaturedDealsResponse(BaseModel):
    count: int
    deals: list[FeaturedDealResponse] = Field(default_factory=list)


@router.get("", response_model=FeaturedDealsResponse)
def get_featured_deals(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=48)] = 24,
) -> FeaturedDealsResponse:
    deals = list_featured_deals(db, limit=limit)
    return FeaturedDealsResponse(
        count=len(deals),
        deals=[FeaturedDealResponse(**deal) for deal in deals],
    )
