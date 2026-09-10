"""Summarise the live Amazon offer list into a "you're not stuck with the buy box" view.

One ASIN on Amazon has many sellers at different prices — a buy box, other
third-party *new* listings, and used / renewed stock. The price verdict only
looks at the buy box; this adds the spread around it so a shopper can see
"buy box $130, another new from $118, used from $99" without leaving SaveIQ.

Deterministic, no ranking beyond price. Returns ``None`` when the buy box is the
only thing worth showing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.base import ProviderOffer

# Keep an alternate-new offer only if it is at least this far below the buy box —
# a marketplace echo of the buy box itself isn't news.
_NEW_MARGIN = 0.01


@dataclass(frozen=True)
class SpreadTier:
    condition: str  # "new" | "used"
    lowest_total_cents: int
    offer_count: int
    fba_available: bool


@dataclass(frozen=True)
class AmazonOfferSpread:
    buy_box_cents: int
    currency: str
    lowest_overall_cents: int
    savings_vs_buy_box_cents: int  # >= 0; 0 when the buy box is already the lowest
    tiers: list[SpreadTier] = field(default_factory=list)


def _bucket(condition: str) -> str | None:
    c = condition.lower()
    if c == "new":
        return "new"
    if c in ("used", "refurbished"):
        return "used"
    return None  # collectible / unknown — don't surface


def summarize_amazon_offers(
    offers: list[ProviderOffer],
    *,
    buy_box_cents: int | None,
    currency: str,
) -> AmazonOfferSpread | None:
    if buy_box_cents is None or buy_box_cents <= 0:
        return None

    priced: dict[str, list[ProviderOffer]] = {"new": [], "used": []}
    for offer in offers:
        total = offer.total_cents
        if total is None or total <= 0:
            continue
        bucket = _bucket(offer.condition)
        if bucket is not None:
            priced[bucket].append(offer)

    tiers: list[SpreadTier] = []
    lowest_overall = buy_box_cents

    new_alts = [
        o
        for o in priced["new"]
        if not o.is_buy_box and (o.total_cents or 0) <= round(buy_box_cents * (1 - _NEW_MARGIN))
    ]
    if new_alts:
        low = min(o.total_cents or 0 for o in new_alts)
        tiers.append(
            SpreadTier(
                condition="new",
                lowest_total_cents=low,
                offer_count=len(new_alts),
                fba_available=any((o.metadata or {}).get("is_fba") for o in new_alts),
            )
        )
        lowest_overall = min(lowest_overall, low)

    if priced["used"]:
        low = min(o.total_cents or 0 for o in priced["used"])
        tiers.append(
            SpreadTier(
                condition="used",
                lowest_total_cents=low,
                offer_count=len(priced["used"]),
                fba_available=any((o.metadata or {}).get("is_fba") for o in priced["used"]),
            )
        )
        lowest_overall = min(lowest_overall, low)

    if not tiers:
        return None

    return AmazonOfferSpread(
        buy_box_cents=buy_box_cents,
        currency=currency,
        lowest_overall_cents=lowest_overall,
        savings_vs_buy_box_cents=max(0, buy_box_cents - lowest_overall),
        tiers=tiers,
    )
