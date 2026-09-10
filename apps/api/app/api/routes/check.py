"""Public price-check endpoint (CP16).

No auth. Per-IP rate limited (only when ``RATE_LIMIT_ENABLED``) because each call
spends a provider token. Returns the same shape as the admin surface.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.providers import get_provider_registry
from app.services.decision.deal_score import DealAssessment
from app.services.decision.price_check import PriceCheckError, run_price_check
from app.services.endpoint_limit import allow

router = APIRouter(prefix="/check", tags=["check"])


class SparkPointOut(BaseModel):
    t: str
    c: int


class MerchantOfferOut(BaseModel):
    merchant: str
    price_cents: int
    currency: str
    url: str | None
    match_confidence: float


class ComparisonOut(BaseModel):
    reference_merchant: str
    reference_price_cents: int
    currency: str
    offers: list[MerchantOfferOut]
    cheapest: MerchantOfferOut | None


class SpreadTierOut(BaseModel):
    condition: str
    lowest_total_cents: int
    offer_count: int
    fba_available: bool


class AmazonSpreadOut(BaseModel):
    buy_box_cents: int
    currency: str
    lowest_overall_cents: int
    savings_vs_buy_box_cents: int
    tiers: list[SpreadTierOut]


class CheckResponse(BaseModel):
    provider: str
    provider_product_id: str
    title: str | None
    product_url: str | None
    currency: str
    assessment: DealAssessment
    sparkline: list[SparkPointOut]
    comparison: ComparisonOut | None = None
    spread: AmazonSpreadOut | None = None


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("", response_model=CheckResponse)
async def check_price(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str | None, Query(max_length=2048)] = None,
    product_id: Annotated[str | None, Query(min_length=3, max_length=32)] = None,
    days: Annotated[int, Query(ge=7, le=365)] = 90,
) -> CheckResponse:
    settings: Settings = get_settings()
    if not allow("check", _client_ip(request), per_minute=settings.check_rate_per_minute):
        raise HTTPException(status_code=429, detail="too many checks — try again in a minute")

    try:
        result = await run_price_check(
            get_provider_registry(),
            product_id=product_id,
            url=url,
            days=days,
            db=db,
        )
    except PriceCheckError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    db.commit()

    comparison_out: ComparisonOut | None = None
    if result.comparison is not None:
        c = result.comparison
        comparison_out = ComparisonOut(
            reference_merchant=c.reference_merchant,
            reference_price_cents=c.reference_price_cents,
            currency=c.currency,
            offers=[
                MerchantOfferOut(
                    merchant=o.merchant,
                    price_cents=o.price_cents,
                    currency=o.currency,
                    url=o.url,
                    match_confidence=o.match_confidence,
                )
                for o in c.offers
            ],
            cheapest=(
                MerchantOfferOut(
                    merchant=c.cheapest.merchant,
                    price_cents=c.cheapest.price_cents,
                    currency=c.cheapest.currency,
                    url=c.cheapest.url,
                    match_confidence=c.cheapest.match_confidence,
                )
                if c.cheapest
                else None
            ),
        )

    spread_out: AmazonSpreadOut | None = None
    if result.spread is not None:
        s = result.spread
        spread_out = AmazonSpreadOut(
            buy_box_cents=s.buy_box_cents,
            currency=s.currency,
            lowest_overall_cents=s.lowest_overall_cents,
            savings_vs_buy_box_cents=s.savings_vs_buy_box_cents,
            tiers=[
                SpreadTierOut(
                    condition=t.condition,
                    lowest_total_cents=t.lowest_total_cents,
                    offer_count=t.offer_count,
                    fba_available=t.fba_available,
                )
                for t in s.tiers
            ],
        )

    return CheckResponse(
        provider=result.provider,
        provider_product_id=result.provider_product_id,
        title=result.title,
        product_url=result.product_url,
        currency=result.currency,
        assessment=result.assessment,
        sparkline=[SparkPointOut(t=p.t, c=p.c) for p in result.sparkline],
        comparison=comparison_out,
        spread=spread_out,
    )
