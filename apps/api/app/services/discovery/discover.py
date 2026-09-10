"""Run a structured shopping query against the catalogue we can reach (Keepa
search) and return candidates with a current price.

Deliberately cheap: one Keepa ``/search`` call, then a current price for the top
``_PRICE_PROBE`` candidates (concurrently) — discovery is a storefront, so a row
without a price reads as broken. A budget, when given, also filters and reorders.
The full verdict is left to ``/check`` when the shopper clicks through.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from app.providers import ProviderCapability, ProviderError
from app.providers.registry import ProviderRegistry
from app.services.discovery.query import ShoppingQuery

logger = logging.getLogger(__name__)

_SEARCH_LIMIT = 12
_PRICE_PROBE = 6  # candidates we spend a (concurrent) price call on per search


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
    if hits:
        probed = True
        to_probe = hits[: min(_PRICE_PROBE, limit)]

        async def _price(hit: DiscoverHit) -> DiscoverHit:
            try:
                price = await adapter.get_price(hit.product_id)
            except ProviderError:
                return hit
            if price is None or price.price_cents is None:
                return hit
            return hit.model_copy(
                update={
                    "price_cents": price.price_cents,
                    "currency": price.currency,
                    "in_budget": _within(price.price_cents, query) if has_budget else None,
                }
            )

        priced = await asyncio.gather(*(_price(h) for h in to_probe))
        hits = [*priced, *hits[len(to_probe) :]]
        # priced first (in-budget ahead of over-budget), unpriced last; price asc within
        hits.sort(
            key=lambda h: (
                h.price_cents is None,
                h.in_budget is False,
                h.price_cents if h.price_cents is not None else 1 << 62,
            )
        )

    return DiscoverResult(query=query, hits=hits[:limit], price_probed=probed)


def _within(price_cents: int, query: ShoppingQuery) -> bool:
    if query.price_max_cents is not None and price_cents > query.price_max_cents:
        return False
    if query.price_min_cents is not None and price_cents < query.price_min_cents:
        return False
    return True
