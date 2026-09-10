"""Run a structured shopping query against the catalogue we can reach (Keepa
search) and return candidates, price-filtered when a budget was given.

Deliberately cheap: one Keepa ``/search`` call, then a current price for at most
``_PRICE_PROBE`` candidates only when the query carries a budget. The full
verdict is left to ``/check`` when the shopper clicks through.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.providers import ProviderCapability, ProviderError
from app.providers.registry import ProviderRegistry
from app.services.discovery.query import ShoppingQuery

logger = logging.getLogger(__name__)

_SEARCH_LIMIT = 12
_PRICE_PROBE = 6  # how many candidates we'll spend a price call on to budget-filter


class DiscoverHit(BaseModel):
    product_id: str
    title: str
    brand: str | None = None
    image_url: str | None = None
    price_cents: int | None = None
    currency: str = "CAD"
    in_budget: bool | None = None  # None = price unknown / not probed


class DiscoverResult(BaseModel):
    query: ShoppingQuery
    hits: list[DiscoverHit]
    price_probed: bool


async def discover(
    registry: ProviderRegistry,
    query: ShoppingQuery,
    *,
    limit: int = 8,
) -> DiscoverResult:
    adapter = registry.try_get("keepa")
    if adapter is None or ProviderCapability.search not in adapter.capabilities:
        return DiscoverResult(query=query, hits=[], price_probed=False)

    try:
        products = await adapter.search_products(query.search_terms, limit=_SEARCH_LIMIT)
    except ProviderError:
        logger.warning("discover search failed", exc_info=True)
        return DiscoverResult(query=query, hits=[], price_probed=False)

    hits = [
        DiscoverHit(
            product_id=p.provider_product_id,
            title=p.title,
            brand=p.brand,
            image_url=p.image_url,
            currency=p.currency or "CAD",
        )
        for p in products
        if p.provider_product_id
    ]

    has_budget = query.price_max_cents is not None or query.price_min_cents is not None
    probed = False
    if has_budget and hits:
        probed = True
        kept: list[DiscoverHit] = []
        for hit in hits[:_PRICE_PROBE]:
            try:
                price = await adapter.get_price(hit.product_id)
            except ProviderError:
                price = None
            if price is not None and price.price_cents is not None:
                hit = hit.model_copy(
                    update={
                        "price_cents": price.price_cents,
                        "currency": price.currency,
                        "in_budget": _within(price.price_cents, query),
                    }
                )
            kept.append(hit)
        # in-budget first, then unknown price, then out of budget; price asc within
        kept.sort(
            key=lambda h: (h.in_budget is False, h.in_budget is None, h.price_cents or 1 << 62)
        )
        hits = kept

    return DiscoverResult(query=query, hits=hits[:limit], price_probed=probed)


def _within(price_cents: int, query: ShoppingQuery) -> bool:
    if query.price_max_cents is not None and price_cents > query.price_max_cents:
        return False
    if query.price_min_cents is not None and price_cents < query.price_min_cents:
        return False
    return True
