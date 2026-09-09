"""Shared price-check flow: (URL | id) -> provider fetch -> decision engine.

Used by both the admin surface and the public CP16 endpoint so the two never
drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.providers import ProviderCapability, ProviderError, ProviderProductNotFound
from app.providers.base import ProductDataProvider, ProviderPriceHistory
from app.providers.registry import ProviderRegistry
from app.services.decision.assess import assess_from_provider
from app.services.decision.comparison_cache import resolve_comparison
from app.services.decision.deal_score import DealAssessment
from app.services.decision.matching import Comparison, build_comparison
from app.services.product_url import extract_product_ref

logger = logging.getLogger(__name__)

# Points in the compact series the UI draws as a sparkline.
SPARKLINE_MAX_POINTS = 60


class PriceCheckError(Exception):
    """Carries an HTTP status + detail for the route layer to surface."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class SparkPoint:
    t: str  # ISO date
    c: int  # price cents


@dataclass(frozen=True)
class PriceCheckResult:
    provider: str
    provider_product_id: str
    title: str | None
    product_url: str | None
    assessment: DealAssessment
    currency: str = "CAD"
    sparkline: list[SparkPoint] = field(default_factory=list)
    comparison: Comparison | None = None


async def _build_comparison(
    registry: ProviderRegistry,
    db: Session | None,
    *,
    reference_provider: str,
    provider_product_id: str,
    market: str,
    title: str | None,
    brand: str | None,
    reference_price_cents: int,
    currency: str,
    now: datetime | None = None,
) -> Comparison | None:
    """Cross-merchant offers from the comparison cache. Never raises.

    The cache is task-backed (DataForSEO has no live endpoint): the first check of
    a cold product returns ``None`` and primes a task; later checks render the
    comparison from cached offers. ``db is None`` disables it entirely.
    """

    if not title or db is None:
        return None
    candidates = await resolve_comparison(
        db,
        registry,
        provider=reference_provider,
        provider_product_id=provider_product_id,
        market=market,
        title=title,
        brand=brand,
        currency=currency,
        now=now,
    )
    if not candidates:
        return None
    return build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=title,
        reference_brand=brand,
        reference_price_cents=reference_price_cents,
        currency=currency,
        candidates=candidates,
    )


def _build_sparkline(history: ProviderPriceHistory) -> list[SparkPoint]:
    """Down-sample the (already daily, one-kind) history to <= SPARKLINE_MAX_POINTS."""

    points = sorted(history.points, key=lambda p: p.observed_at)
    if not points:
        return []
    # ceil division so a 90-point series with a 60 cap steps by 2, not 1.
    step = max(1, -(-len(points) // SPARKLINE_MAX_POINTS))
    sampled = points[::step]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return [SparkPoint(t=p.observed_at.date().isoformat(), c=p.price_cents) for p in sampled]


def _pick_provider(
    registry: ProviderRegistry,
    *,
    name: str | None,
    hint: str | None,
) -> ProductDataProvider:
    if name:
        adapter = registry.try_get(name)
        if adapter is None:
            raise PriceCheckError(404, f"no provider named {name!r}")
        return adapter
    if hint and hint in registry:
        return registry.get(hint)
    for adapter in registry.list():
        caps = adapter.capabilities
        if ProviderCapability.get_price in caps and ProviderCapability.price_history in caps:
            return adapter
    raise PriceCheckError(503, "no configured provider can price-check")


def resolve_target(product_id: str | None, url: str | None) -> tuple[str, str | None]:
    """(provider_product_id, provider_name_hint). Raises PriceCheckError."""

    if url:
        ref = extract_product_ref(url, follow_redirects=True)
        if ref is None:
            raise PriceCheckError(422, "could not find a product id in that URL")
        if ref.market not in ("", "CA"):
            raise PriceCheckError(
                422, f"{ref.retailer} {ref.market} is not covered yet — only Amazon.ca"
            )
        return ref.product_id, ("keepa" if ref.keepa_domain == 6 else None)
    if product_id:
        return product_id.strip().upper(), None
    raise PriceCheckError(422, "pass product_id or url")


async def run_price_check(
    registry: ProviderRegistry,
    *,
    product_id: str | None = None,
    url: str | None = None,
    provider: str | None = None,
    days: int = 90,
    db: Session | None = None,
    now: datetime | None = None,
) -> PriceCheckResult:
    resolved_id, hint = resolve_target(product_id, url)
    adapter = _pick_provider(registry, name=provider, hint=hint)

    try:
        price = await adapter.get_price(resolved_id)
        if price is None or price.price_cents is None:
            raise PriceCheckError(404, "no current price for that product")
        history = await adapter.get_price_history(resolved_id, days=days)
        if history is None:
            raise PriceCheckError(404, "no price history for that product")
        product = await adapter.get_product(resolved_id)
    except ProviderProductNotFound as exc:
        raise PriceCheckError(404, str(exc)) from exc
    except ProviderError as exc:
        raise PriceCheckError(502, f"provider error: {exc}") from exc

    assessment = assess_from_provider(price, history)
    if assessment is None:
        raise PriceCheckError(422, "no current price to assess")

    title = product.title if product else None
    comparison = await _build_comparison(
        registry,
        db,
        reference_provider=adapter.name,
        provider_product_id=resolved_id,
        market=adapter.market,
        title=title,
        brand=product.brand if product else None,
        reference_price_cents=assessment.effective_price.effective_cents,
        currency=price.currency,
        now=now,
    )

    return PriceCheckResult(
        provider=adapter.name,
        provider_product_id=resolved_id,
        title=title,
        product_url=product.product_url if product else None,
        assessment=assessment,
        currency=price.currency,
        sparkline=_build_sparkline(history),
        comparison=comparison,
    )
