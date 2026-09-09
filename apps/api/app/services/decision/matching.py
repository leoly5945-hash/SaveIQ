"""CP7 — decide which cross-merchant offers are the *same product*.

Deterministic and conservative: it is better to drop a real match than to show
"Walmart $40" next to a $900 power station because the title happened to share a
few words. No ML, no merchant preference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.providers.base import ProviderOffer

# A candidate priced outside this multiple of the reference is a bundle, an
# accessory, or a mismatch — not the same product.
_PRICE_LOW_RATIO = 0.45
_PRICE_HIGH_RATIO = 2.4
# Keep a candidate at or above this blended confidence.
_MIN_CONFIDENCE = 0.55
# Only call another merchant "cheaper" if it beats the reference by this much.
_CHEAPER_MARGIN = 0.02

_ACCESSORY_TOKENS = frozenset(
    {
        "case",
        "cover",
        "sleeve",
        "skin",
        "decal",
        "protector",
        "charger",
        "cable",
        "adapter",
        "mount",
        "stand",
        "replacement",
        "compatible",
        "for",
        "fits",
        "accessory",
        "kit",
        "bundle",
        "warranty",
        "refurbished",
        "renewed",
        "used",
        "open",
        "box",
    }
)

_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "with", "of", "in", "for", "to", "by", "new"}
)


@dataclass(frozen=True)
class MerchantOffer:
    merchant: str
    price_cents: int
    currency: str
    url: str | None
    match_confidence: float


@dataclass
class Comparison:
    reference_merchant: str
    reference_price_cents: int
    currency: str
    offers: list[MerchantOffer] = field(default_factory=list)
    cheapest: MerchantOffer | None = None  # only set when it beats the reference


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.casefold()).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if t and t not in _STOPWORDS}


def _title_overlap(reference: set[str], candidate: set[str]) -> float:
    if not reference or not candidate:
        return 0.0
    inter = len(reference & candidate)
    # Recall against the reference matters more than precision — a marketplace
    # title is often longer ("… 2010Wh 1500W Solar Generator Portable").
    return inter / len(reference)


def _looks_like_accessory(candidate_tokens: set[str], reference_tokens: set[str]) -> bool:
    extra = candidate_tokens - reference_tokens
    return bool(extra & _ACCESSORY_TOKENS)


def score_candidate(
    *,
    reference_title: str,
    reference_brand: str | None,
    reference_price_cents: int,
    candidate_title: str | None,
    candidate_price_cents: int | None,
) -> float:
    """Blended 0..1 confidence that the candidate is the same product."""

    if not candidate_title or not candidate_price_cents or reference_price_cents <= 0:
        return 0.0

    ref_tokens = _tokens(reference_title)
    cand_tokens = _tokens(candidate_title)
    if _looks_like_accessory(cand_tokens, ref_tokens):
        return 0.0

    ratio = candidate_price_cents / reference_price_cents
    if not (_PRICE_LOW_RATIO <= ratio <= _PRICE_HIGH_RATIO):
        return 0.0

    overlap = _title_overlap(ref_tokens, cand_tokens)
    brand_ok = 1.0
    if reference_brand:
        brand_ok = 1.0 if _norm(reference_brand) in _norm(candidate_title) else 0.0
        if brand_ok == 0.0:
            return 0.0

    # Price closeness: 1.0 at parity, tapering to 0 at the band edges.
    price_close = max(0.0, 1.0 - abs(ratio - 1.0) / (_PRICE_HIGH_RATIO - 1.0))

    return round(0.6 * overlap + 0.25 * brand_ok + 0.15 * price_close, 4)


def build_comparison(
    *,
    reference_merchant: str,
    reference_title: str,
    reference_brand: str | None,
    reference_price_cents: int,
    currency: str,
    candidates: list[ProviderOffer],
) -> Comparison:
    """Match ``candidates`` to the reference product and rank the survivors."""

    best_per_merchant: dict[str, MerchantOffer] = {}
    for offer in candidates:
        merchant = offer.merchant.strip()
        if not merchant or offer.total_cents is None:
            continue
        # Skip a marketplace echo of the same retailer we already have.
        if merchant.casefold() == reference_merchant.casefold():
            continue
        confidence = score_candidate(
            reference_title=reference_title,
            reference_brand=reference_brand,
            reference_price_cents=reference_price_cents,
            candidate_title=(offer.metadata or {}).get("title") or offer.merchant,
            candidate_price_cents=offer.total_cents,
        )
        if confidence < _MIN_CONFIDENCE:
            continue
        matched = MerchantOffer(
            merchant=merchant,
            price_cents=offer.total_cents,
            currency=offer.currency or currency,
            url=offer.url,
            match_confidence=confidence,
        )
        existing = best_per_merchant.get(merchant)
        if existing is None or matched.price_cents < existing.price_cents:
            best_per_merchant[merchant] = matched

    offers = sorted(best_per_merchant.values(), key=lambda o: o.price_cents)
    cheapest: MerchantOffer | None = None
    if offers and offers[0].price_cents <= round(reference_price_cents * (1 - _CHEAPER_MARGIN)):
        cheapest = offers[0]

    return Comparison(
        reference_merchant=reference_merchant,
        reference_price_cents=reference_price_cents,
        currency=currency,
        offers=offers,
        cheapest=cheapest,
    )
