"""Shared price-check flow: (URL | id) -> provider fetch -> decision engine.

Used by both the admin surface and the public CP16 endpoint so the two never
drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.providers import ProviderCapability, ProviderError, ProviderProductNotFound
from app.providers.base import ProductDataProvider, ProviderPriceHistory
from app.providers.registry import ProviderRegistry
from app.services.decision.assess import assess_from_provider
from app.services.decision.deal_score import DealAssessment
from app.services.product_url import extract_product_ref

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

    return PriceCheckResult(
        provider=adapter.name,
        provider_product_id=resolved_id,
        title=product.title if product else None,
        product_url=product.product_url if product else None,
        assessment=assessment,
        currency=price.currency,
        sparkline=_build_sparkline(history),
    )
