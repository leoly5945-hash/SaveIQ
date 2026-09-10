"""Public acquisition advisor (Layer 2) for a real product.

No auth, per-IP rate limited (it spends a Keepa token to resolve the product).
Resolves an ASIN to its price + category + brand, composes the acquisition
options, and ranks them for the given buyer profile. The price verdict lives at
``/check``; this is the "how should I get it" companion.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.settings import Settings, get_settings
from app.providers import ProviderCapability, ProviderError, get_provider_registry
from app.providers.base import ProductDataProvider
from app.services.acquisition import (
    BuyerProfile,
    PathRecommendation,
    compare_paths,
    compose_options,
)
from app.services.acquisition.product_map import infer_product_context
from app.services.decision.price_check import PriceCheckError, resolve_target
from app.services.endpoint_limit import allow

router = APIRouter(prefix="/acquire", tags=["acquire"])


class AcquireResponse(BaseModel):
    product_id: str
    title: str | None
    category: str
    recommendation: PathRecommendation


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _keepa() -> ProductDataProvider:
    registry = get_provider_registry()
    adapter = registry.try_get("keepa")
    if adapter is None or ProviderCapability.get_product not in adapter.capabilities:
        raise HTTPException(status_code=503, detail="no product provider configured")
    return adapter


@router.get("", response_model=AcquireResponse)
async def acquire(
    request: Request,
    url: Annotated[str | None, Query(max_length=2048)] = None,
    product_id: Annotated[str | None, Query(min_length=3, max_length=32)] = None,
    horizon_months: Annotated[int, Query(ge=1, le=120)] = 36,
    annual_discount_rate: Annotated[float, Query(ge=0.0, le=0.5)] = 0.0,
    upgrades_every_months: Annotated[int | None, Query(ge=1, le=120)] = None,
    is_business: Annotated[bool, Query()] = False,
    service_sensitivity: Annotated[Literal["low", "normal", "high"], Query()] = "normal",
) -> AcquireResponse:
    settings: Settings = get_settings()
    if not allow("acquire", _client_ip(request), per_minute=settings.acquire_rate_per_minute):
        raise HTTPException(status_code=429, detail="too many lookups — try again in a minute")

    try:
        resolved_id, _hint = resolve_target(product_id, url)
    except PriceCheckError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    adapter = _keepa()
    try:
        product = await adapter.get_product(resolved_id)
        price = await adapter.get_price(resolved_id)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"provider error: {exc}") from exc
    if price is None or price.price_cents is None:
        raise HTTPException(status_code=404, detail="no current price for that product")

    ctx = infer_product_context(
        price_cents=price.price_cents,
        category=product.category if product else None,
        brand=product.brand if product else None,
        title=product.title if product else None,
    )
    options = compose_options(ctx, horizon_months=horizon_months)
    if not options:
        raise HTTPException(status_code=404, detail="no acquisition options for that product")

    profile = BuyerProfile(
        horizon_months=horizon_months,
        annual_discount_rate=annual_discount_rate,
        upgrades_every_months=upgrades_every_months,
        is_business=is_business,
        service_sensitivity=service_sensitivity,
    )
    return AcquireResponse(
        product_id=resolved_id,
        title=product.title if product else None,
        category=ctx.category,
        recommendation=compare_paths(options, profile, product_slug=resolved_id),
    )
