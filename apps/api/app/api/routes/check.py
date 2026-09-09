"""Public price-check endpoint (CP16).

No auth. Per-IP rate limited (only when ``RATE_LIMIT_ENABLED``) because each call
spends a provider token. Returns the same shape as the admin surface.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.settings import Settings, get_settings
from app.providers import get_provider_registry
from app.services.decision.deal_score import DealAssessment
from app.services.decision.price_check import PriceCheckError, run_price_check
from app.services.endpoint_limit import allow

router = APIRouter(prefix="/check", tags=["check"])


class SparkPointOut(BaseModel):
    t: str
    c: int


class CheckResponse(BaseModel):
    provider: str
    provider_product_id: str
    title: str | None
    product_url: str | None
    currency: str
    assessment: DealAssessment
    sparkline: list[SparkPointOut]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("", response_model=CheckResponse)
async def check_price(
    request: Request,
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
        )
    except PriceCheckError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return CheckResponse(
        provider=result.provider,
        provider_product_id=result.provider_product_id,
        title=result.title,
        product_url=result.product_url,
        currency=result.currency,
        assessment=result.assessment,
        sparkline=[SparkPointOut(t=p.t, c=p.c) for p in result.sparkline],
    )
