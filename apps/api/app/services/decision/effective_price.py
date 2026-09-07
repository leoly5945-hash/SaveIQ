"""CP10 — effective price.

The *effective price* is what the shopper actually pays out the door, after
deterministic, always-applicable adjustments: shipping, and (later) auto-applied
coupons or guaranteed cashback. It is **not** a discount claim and never uses a
merchant's strike-through "list price".

For the Keepa / Amazon MVP this is just ``base + shipping`` — the structure keeps
a hook for coupon / cashback components without pretending we have them yet.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.providers.base import ProviderOffer, ProviderPrice


class EffectivePriceComponent(BaseModel):
    label: str
    amount_cents: int  # signed: negative reduces the price


class EffectivePrice(BaseModel):
    base_price_cents: int
    effective_cents: int
    currency: str
    components: list[EffectivePriceComponent] = Field(default_factory=list)

    @property
    def savings_vs_base_cents(self) -> int:
        return self.base_price_cents - self.effective_cents


def compute_effective_price(
    base_price_cents: int,
    *,
    currency: str,
    shipping_cents: int = 0,
    extra_components: list[EffectivePriceComponent] | None = None,
) -> EffectivePrice:
    """Base price plus shipping plus any deterministic extra components.

    ``extra_components`` amounts are signed — a coupon is negative. Nothing here
    is speculative: only pass a component the shopper is guaranteed to get.
    """

    components: list[EffectivePriceComponent] = []
    if shipping_cents and shipping_cents > 0:
        components.append(EffectivePriceComponent(label="Shipping", amount_cents=shipping_cents))
    components.extend(extra_components or [])

    effective = base_price_cents + sum(c.amount_cents for c in components)
    return EffectivePrice(
        base_price_cents=base_price_cents,
        effective_cents=max(effective, 0),
        currency=currency,
        components=components,
    )


def effective_price_from_provider(
    price: ProviderPrice,
    *,
    offer: ProviderOffer | None = None,
) -> EffectivePrice | None:
    """Effective price for a :class:`ProviderPrice`, folding in offer shipping."""

    if price.price_cents is None:
        return None
    shipping = 0
    if offer is not None and offer.shipping_cents and offer.shipping_cents > 0:
        shipping = offer.shipping_cents
    return compute_effective_price(
        price.price_cents,
        currency=price.currency,
        shipping_cents=shipping,
    )
