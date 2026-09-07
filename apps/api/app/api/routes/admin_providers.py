"""Admin: inspect product data providers + run a live deal assessment (CP4, CP9–CP11).

Read-only. `GET /admin/providers` confirms which providers are wired without
exposing a secret. `GET /admin/providers/price-check` live-fetches one product
and runs the deterministic decision engine over it — the staging surface for
"show me it works on real data" before the public price-checker (CP16) exists.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.providers import ProviderCapability, ProviderError, get_provider_registry
from app.providers.base import ProductDataProvider
from app.services.decision.assess import assess_from_provider
from app.services.decision.deal_score import DealAssessment

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/providers",
    tags=["admin-providers"],
    dependencies=[Depends(require_admin)],
)


class ProviderInfo(BaseModel):
    name: str
    market: str
    currency: str
    configured: bool
    capabilities: list[str]


class ProviderListResponse(BaseModel):
    count: int
    providers: list[ProviderInfo]


class PriceCheckResponse(BaseModel):
    provider: str
    provider_product_id: str
    title: str | None
    product_url: str | None
    assessment: DealAssessment


@router.get("", response_model=ProviderListResponse)
def list_providers() -> ProviderListResponse:
    registry = get_provider_registry()
    infos = [
        ProviderInfo(
            name=provider.name,
            market=provider.market,
            currency=provider.currency,
            configured=provider.is_configured(),
            capabilities=sorted(str(cap) for cap in provider.capabilities),
        )
        for provider in registry.list()
    ]
    infos.sort(key=lambda info: info.name)
    return ProviderListResponse(count=len(infos), providers=infos)


def _pick_provider(name: str | None) -> ProductDataProvider:
    registry = get_provider_registry()
    if name:
        provider = registry.try_get(name)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"no provider named {name!r}")
        return provider
    for provider in registry.list():
        caps = provider.capabilities
        if ProviderCapability.get_price in caps and ProviderCapability.price_history in caps:
            return provider
    raise HTTPException(
        status_code=503,
        detail="no configured provider can answer get_price + price_history",
    )


@router.get("/price-check")
async def price_check(
    product_id: Annotated[
        str, Query(min_length=3, max_length=32, description="ASIN / provider product id")
    ],
    provider: Annotated[str | None, Query()] = None,
    days: Annotated[int, Query(ge=7, le=365)] = 90,
    debug: Annotated[
        bool, Query(description="return raw provider data, not an assessment")
    ] = False,
) -> object:
    adapter = _pick_provider(provider)
    if debug:
        describe = getattr(adapter, "describe", None)
        if describe is None:
            raise HTTPException(status_code=400, detail=f"{adapter.name} has no debug describe()")
        try:
            return await describe(product_id)
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=f"provider error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("describe failed", extra={"product_id": product_id})
            raise HTTPException(
                status_code=502, detail=f"describe failed: {type(exc).__name__}: {exc}"
            ) from exc
    try:
        price = await adapter.get_price(product_id)
        if price is None:
            raise HTTPException(status_code=404, detail="provider has no price for that id")
        history = await adapter.get_price_history(product_id, days=days)
        if history is None:
            raise HTTPException(status_code=404, detail="provider has no price history for that id")
        product = await adapter.get_product(product_id)
        assessment = assess_from_provider(price, history)
    except HTTPException:
        raise
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"provider error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - surface the real cause, don't 500 blank
        logger.exception("price-check failed", extra={"product_id": product_id})
        raise HTTPException(
            status_code=502, detail=f"assessment failed: {type(exc).__name__}: {exc}"
        ) from exc

    if assessment is None:
        raise HTTPException(status_code=422, detail="no current price to assess")

    return PriceCheckResponse(
        provider=adapter.name,
        provider_product_id=product_id,
        title=product.title if product else None,
        product_url=product.product_url if product else None,
        assessment=assessment,
    )
