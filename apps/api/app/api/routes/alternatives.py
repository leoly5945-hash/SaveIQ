"""Public "buy this instead" endpoint (Layer 3).

Given a product that's a poor buy right now, return a few similar ones that are a
good buy. No auth, hard per-IP rate limit — it runs a search plus a lightweight
verdict on several candidates.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.settings import Settings, get_settings
from app.providers import ProviderCapability, ProviderError, get_provider_registry
from app.services.decision.price_check import PriceCheckError, resolve_target
from app.services.discovery.alternatives import AlternativesResult, find_alternatives
from app.services.endpoint_limit import allow

router = APIRouter(prefix="/alternatives", tags=["alternatives"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("", response_model=AlternativesResult)
async def alternatives(
    request: Request,
    url: Annotated[str | None, Query(max_length=2048)] = None,
    product_id: Annotated[str | None, Query(min_length=3, max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=5)] = 3,
) -> AlternativesResult:
    settings: Settings = get_settings()
    if not allow("alternatives", _client_ip(request), per_minute=settings.discover_rate_per_minute):
        raise HTTPException(status_code=429, detail="too many lookups — try again in a minute")

    try:
        resolved_id, _hint = resolve_target(product_id, url)
    except PriceCheckError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    registry = get_provider_registry()
    adapter = registry.try_get("keepa")
    if adapter is None or ProviderCapability.get_product not in adapter.capabilities:
        raise HTTPException(status_code=503, detail="no product provider configured")

    try:
        product = await adapter.get_product(resolved_id)
        price = await adapter.get_price(resolved_id)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"provider error: {exc}") from exc
    if price is None or price.price_cents is None:
        raise HTTPException(status_code=404, detail="no current price for that product")

    return await find_alternatives(
        registry,
        reference_product_id=resolved_id,
        reference_price_cents=price.price_cents,
        title=product.title if product else None,
        category=product.category if product else None,
        brand=product.brand if product else None,
        limit=limit,
    )
