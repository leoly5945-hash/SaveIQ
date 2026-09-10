"""When a product is a WAIT, find a similar one that's a BUY right now.

Reuses :func:`app.services.discovery.discover.discover` for the search + a
price filter, then runs the *lightweight* verdict (price + history only — no
offers, comparison, or acquisition) on the cheaper candidates and keeps the ones
that come back BUY / FAIR.

Token-heavy (a couple of Keepa calls per candidate, softened by the provider's
60-second product cache), so it is behind its own endpoint and only worth calling
when the checked product's own verdict is WAIT / UNKNOWN.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from app.providers import ProviderCapability, ProviderError
from app.providers.registry import ProviderRegistry
from app.services.decision.assess import assess_from_provider
from app.services.discovery.discover import discover
from app.services.discovery.query import ShoppingQuery

logger = logging.getLogger(__name__)

_MAX_CANDIDATES_PROBED = 6
_GOOD_VERDICTS = ("BUY", "FAIR")
_TITLE_STOP = frozenset(
    {"the", "a", "an", "and", "or", "with", "for", "of", "new", "pack", "set", "kit"}
)


class AlternativeHit(BaseModel):
    product_id: str
    title: str
    price_cents: int
    currency: str
    verdict: str
    score: int
    reason: str | None = None


class AlternativesResult(BaseModel):
    reference_product_id: str
    reference_price_cents: int
    search_terms: str
    alternatives: list[AlternativeHit]


def _alt_terms(title: str | None, category: str | None, brand: str | None) -> str:
    if category and category.strip():
        return category.strip()
    words = [
        w
        for w in re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower()).split()
        if w and w not in _TITLE_STOP and not w.isdigit()
    ]
    core = " ".join(words[:3]).strip()
    if brand and brand.strip():
        b = brand.strip().lower()
        if b not in core:
            core = f"{b} {core}".strip()
    return core or (title or "")


async def find_alternatives(
    registry: ProviderRegistry,
    *,
    reference_product_id: str,
    reference_price_cents: int,
    title: str | None,
    category: str | None,
    brand: str | None,
    days: int = 90,
    limit: int = 3,
) -> AlternativesResult:
    terms = _alt_terms(title, category, brand)
    empty = AlternativesResult(
        reference_product_id=reference_product_id,
        reference_price_cents=reference_price_cents,
        search_terms=terms,
        alternatives=[],
    )

    adapter = registry.try_get("keepa")
    if (
        adapter is None
        or not {
            ProviderCapability.search,
            ProviderCapability.get_price,
            ProviderCapability.price_history,
        }
        <= adapter.capabilities
    ):
        return empty
    if not terms or reference_price_cents <= 0:
        return empty

    query = ShoppingQuery(
        raw=terms,
        search_terms=terms,
        price_max_cents=reference_price_cents,
        parser_mode="rules",
    )
    discovered = await discover(registry, query, limit=_MAX_CANDIDATES_PROBED + 2)

    exclude = reference_product_id.strip().upper()
    hits: list[AlternativeHit] = []
    probed = 0
    for cand in discovered.hits:
        if len(hits) >= limit or probed >= _MAX_CANDIDATES_PROBED:
            break
        if cand.product_id.strip().upper() == exclude:
            continue
        if cand.price_cents is not None and cand.price_cents > reference_price_cents:
            continue
        probed += 1
        try:
            price = await adapter.get_price(cand.product_id)
            history = await adapter.get_price_history(cand.product_id, days=days)
        except ProviderError:
            logger.warning("alternative probe failed", exc_info=True)
            continue
        if price is None or price.price_cents is None or history is None:
            continue
        if price.price_cents > reference_price_cents:
            continue
        assessment = assess_from_provider(price, history)
        if assessment is None or assessment.verdict.value not in _GOOD_VERDICTS:
            continue
        hits.append(
            AlternativeHit(
                product_id=cand.product_id,
                title=cand.title,
                price_cents=price.price_cents,
                currency=price.currency,
                verdict=assessment.verdict.value,
                score=assessment.score,
                reason=assessment.reasons[0] if assessment.reasons else None,
            )
        )

    hits.sort(key=lambda h: (h.verdict != "BUY", -h.score, h.price_cents))
    return empty.model_copy(update={"alternatives": hits[:limit]})
