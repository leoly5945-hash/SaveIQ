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
# Same barcode (GTIN) = same product, as long as nothing else (accessory words,
# a conflicting variant, the price band, the brand) says otherwise.
_GTIN_MATCH_CONFIDENCE = 0.9
# "Cheaper at X" is a strong claim — only flag it when the match is solid, not
# merely above the inclusion bar.
_CHEAPEST_MIN_CONFIDENCE = 0.65
# A title-matched offer priced under this share of the reference's own 90-day
# low is dropped (see build_comparison).
_BELOW_LOW_MIN_RATIO = 0.75
# Peer-to-peer resale marketplaces: second-hand goods from individuals, not a
# store price for a new item. (eBay comes from its own API, new-only.)
# eBay as a second place to buy: shown up to this much above the reference.
_EBAY_ALSO_MAX_RATIO = 1.15
# Stores whose name says second-hand, returns or liquidation stock: not a store
# price for a new item ("Liquidation125Plus", "PayMore", "K-W Surplus").
_SECONDHAND_STORE_WORDS = (
    "liquidation",
    "surplus",
    "paymore",
    "pawn",
    "refurb",
    "secondhand",
    "second hand",
    "thrift",
    "preowned",
    "pre owned",
)
_RESALE_MARKETPLACES = (
    "poshmark",
    "kijiji",
    "mercari",
    "depop",
    "vinted",
    "facebook marketplace",
    "craigslist",
    "varagesale",
    "thredup",
)
# Only call another merchant "cheaper" if it beats the reference by this much.
_CHEAPER_MARGIN = 0.02
# The block answers "can I pay less elsewhere?" — an offer above the reference
# price can't, so it is not shown (and foreign resellers priced 1.5x+ were noise).
_DISPLAY_MAX_RATIO = 1.0

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
    # Shown under the merchant name, e.g. "New · seller 99.8% positive".
    detail: str | None = None


@dataclass
class Comparison:
    reference_merchant: str
    reference_price_cents: int
    currency: str
    offers: list[MerchantOffer] = field(default_factory=list)
    cheapest: MerchantOffer | None = None  # only set when it beats the reference
    # A new eBay.ca listing that is NOT cheaper than the reference (within
    # _EBAY_ALSO_MAX_RATIO): another place to buy, never a "cheaper at" claim.
    also_on_ebay: MerchantOffer | None = None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.casefold()).strip()


def _tokens(text: str) -> set[str]:
    glued = _SPLIT_SPEC_RE.sub(r"\1\2", _norm(text))
    return {t for t in glued.split() if t and t not in _STOPWORDS}


def _pack_counts(title: str) -> set[int]:
    text = _norm(title)
    return {int(n) for n in _PACK_OF_RE.findall(text) + _COUNT_RE.findall(text)}


def _different_quantity(reference_title: str, candidate_title: str) -> bool:
    """The two listings sell a different number of units.

    A "Pack of 4" toothpaste at $12.99 was "beaten" by a single tube at $5.99,
    and a 20-count battery pack by an 8-count. When the reference is a
    multi-pack the candidate must state the same count — a title with no count
    is almost always the single item. A single-item reference never matches a
    multi-pack either.
    """

    ref, cand = _pack_counts(reference_title), _pack_counts(candidate_title)
    ref_multi = {n for n in ref if n > 1}
    cand_multi = {n for n in cand if n > 1}
    if ref_multi:
        return not (ref_multi & cand)
    return bool(cand_multi)


def _title_overlap(reference: set[str], candidate: set[str]) -> float:
    if not reference or not candidate:
        return 0.0
    inter = len(reference & candidate)
    # Recall against the reference matters more than precision — a marketplace
    # title is often longer ("… 2010Wh 1500W Solar Generator Portable").
    return inter / len(reference)


# "600va", "256gb", "45w", "10000mah": a number with a unit. Two listings that
# both state the same unit but never the same number are different variants.
_SPEC_UNITS = "gb|tb|va|w|wh|mah|in|inch|ft|mm|cm|oz|ml|kg|lb|hz|mp|g|l"
_SPEC_RE = re.compile(rf"^(\d+(?:\.\d+)?)({_SPEC_UNITS})$")
# "70 Ml" / "539 g": glue the number to its unit so it reads as one spec token.
_SPLIT_SPEC_RE = re.compile(rf"\b(\d+) ({_SPEC_UNITS})\b")

# The reference names a weight/volume ("539g") and the candidate doesn't state
# the same one (no size, or only in another unit). Much cheaper + unconfirmed
# size = almost certainly the smaller jar, so it needs to be within this ratio.
_SIZE_UNITS = frozenset({"g", "kg", "ml", "l", "oz", "lb"})
_UNCONFIRMED_SIZE_MIN_RATIO = 0.7

# How many units the listing sells: "Pack of 4", "12 Count", "2-Pack", "20ct".
_PACK_OF_RE = re.compile(r"\b(?:pack|box|set|case|lot) of (\d+)\b")
_COUNT_RE = re.compile(r"\b(\d+) ?(?:count|ct|packs?|pk|pads|rolls|pcs|pieces|pc)\b")


def _specs(tokens: set[str]) -> dict[str, set[str]]:
    specs: dict[str, set[str]] = {}
    for t in tokens:
        m = _SPEC_RE.match(t)
        if m:
            specs.setdefault(m.group(2), set()).add(m.group(1))
    return specs


def _size_unconfirmed(reference: set[str], candidate: set[str]) -> bool:
    ref_specs, cand_specs = _specs(reference), _specs(candidate)
    ref_sizes = {u: v for u, v in ref_specs.items() if u in _SIZE_UNITS}
    if not ref_sizes:
        return False
    return not any(v & cand_specs.get(u, set()) for u, v in ref_sizes.items())


def _model_codes(tokens: set[str]) -> set[str]:
    """Letter+digit tokens that look like part numbers ("be600m1", "cp1500pfclcd")."""

    return {
        t
        for t in tokens
        if len(t) >= 5 and re.search(r"[a-z]", t) and re.search(r"\d", t) and not _SPEC_RE.match(t)
    }


def _conflicting_variant(reference: set[str], candidate: set[str]) -> bool:
    """Both titles name a model number / spec, and they disagree.

    Title overlap alone matched "APC Back-UPS 600VA (BE600M1)" to a cheaper
    "APC Back-UPS 425VA (BE425M)": same words, different product. When both
    sides state part numbers, at least one must be shared; when both state the
    same unit (VA, GB, W…), at least one value must be shared.
    """

    ref_models, cand_models = _model_codes(reference), _model_codes(candidate)
    if ref_models and cand_models and not (ref_models & cand_models):
        return True
    ref_specs, cand_specs = _specs(reference), _specs(candidate)
    for unit in ref_specs.keys() & cand_specs.keys():
        if not (ref_specs[unit] & cand_specs[unit]):
            return True
    return False


def _looks_like_accessory(candidate_tokens: set[str], reference_tokens: set[str]) -> bool:
    extra = candidate_tokens - reference_tokens
    return bool(extra & _ACCESSORY_TOKENS)


def _is_reference_echo(merchant: str, reference_merchant: str) -> bool:
    """A marketplace listing of the same retailer we're comparing against.

    Skips exact matches and same-family names — "Amazon", "Amazon.com",
    "Amazon Warehouse" all echo a reference of "Amazon.ca".
    """

    m = _norm(merchant)
    r = _norm(reference_merchant)
    if not m or m == r:
        return True
    head = r.split(" ", 1)[0] if r else ""
    return bool(head) and (m == head or m.startswith(head + " "))


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
    if _conflicting_variant(ref_tokens, cand_tokens):
        return 0.0
    if _different_quantity(reference_title, candidate_title):
        return 0.0

    ratio = candidate_price_cents / reference_price_cents
    if not (_PRICE_LOW_RATIO <= ratio <= _PRICE_HIGH_RATIO):
        return 0.0
    if ratio < _UNCONFIRMED_SIZE_MIN_RATIO and _size_unconfirmed(ref_tokens, cand_tokens):
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


def _offer_detail(offer: ProviderOffer) -> str | None:
    meta = offer.metadata or {}
    pct = meta.get("seller_feedback_pct")
    if offer.provider != "ebay" or pct is None:
        return None
    score = meta.get("seller_feedback_score") or 0
    return f"New · ships from Canada · seller {pct:g}% positive ({score:,} ratings)"


def build_comparison(
    *,
    reference_merchant: str,
    reference_title: str,
    reference_brand: str | None,
    reference_price_cents: int,
    currency: str,
    candidates: list[ProviderOffer],
    low_90d_cents: int | None = None,
) -> Comparison:
    """Match ``candidates`` to the reference product and rank the survivors.

    ``low_90d_cents`` is the reference retailer's own lowest price in 90 days,
    used to drop weakly-matched offers far below anything the product has
    actually sold for.
    """

    best_per_merchant: dict[str, MerchantOffer] = {}
    also_on_ebay: MerchantOffer | None = None
    for offer in candidates:
        merchant = offer.merchant.strip()
        if not merchant or offer.total_cents is None:
            continue
        if any(name in _norm(merchant) for name in _RESALE_MARKETPLACES):
            continue
        if any(word in _norm(merchant) for word in _SECONDHAND_STORE_WORDS):
            continue
        # Skip a marketplace echo of the same retailer we already have.
        if _is_reference_echo(merchant, reference_merchant):
            continue
        # An offer that isn't cheaper than the reference can't help the shopper —
        # except eBay, kept aside as "also available" when it is close in price.
        not_cheaper = offer.total_cents > round(reference_price_cents * _DISPLAY_MAX_RATIO)
        if not_cheaper and not (
            offer.provider == "ebay"
            and offer.total_cents <= round(reference_price_cents * _EBAY_ALSO_MAX_RATIO)
        ):
            continue
        confidence = score_candidate(
            reference_title=reference_title,
            reference_brand=reference_brand,
            reference_price_cents=reference_price_cents,
            candidate_title=(offer.metadata or {}).get("title") or offer.merchant,
            candidate_price_cents=offer.total_cents,
        )
        meta = offer.metadata or {}
        if confidence > 0 and meta.get("matched_by") == "gtin":
            confidence = max(confidence, _GTIN_MATCH_CONFIDENCE)
        if confidence < _MIN_CONFIDENCE:
            continue
        # A Dyson V8 Plus never under $449.99 on Amazon in 90 days, "matched" at
        # 0.58 to a $279.99 listing: a different variant or a refurb, not a deal.
        # The same went for a V15 Detect Plus (never under $799.99) "matched" at
        # 0.85 to a $499 listing: titles alone can't tell a refurb from new, so
        # only a barcode match may sit that far under the 90-day low.
        if (
            low_90d_cents
            and meta.get("matched_by") != "gtin"
            and offer.total_cents < round(low_90d_cents * _BELOW_LOW_MIN_RATIO)
        ):
            continue
        matched = MerchantOffer(
            merchant=merchant,
            price_cents=offer.total_cents,
            currency=offer.currency or currency,
            url=offer.url,
            match_confidence=confidence,
            detail=_offer_detail(offer),
        )
        if not_cheaper:
            if also_on_ebay is None or matched.price_cents < also_on_ebay.price_cents:
                also_on_ebay = matched
            continue
        existing = best_per_merchant.get(merchant)
        if existing is None or matched.price_cents < existing.price_cents:
            best_per_merchant[merchant] = matched

    offers = sorted(best_per_merchant.values(), key=lambda o: o.price_cents)
    # The cheapest offer we are confident about — a weak match sorted above it
    # must not stop a solid, genuinely cheaper one from being named.
    cheapest = next(
        (
            o
            for o in offers
            if o.match_confidence >= _CHEAPEST_MIN_CONFIDENCE
            and o.price_cents <= round(reference_price_cents * (1 - _CHEAPER_MARGIN))
        ),
        None,
    )

    return Comparison(
        reference_merchant=reference_merchant,
        reference_price_cents=reference_price_cents,
        currency=currency,
        offers=offers,
        cheapest=cheapest,
        # A cheaper eBay listing is already in `offers`; don't show eBay twice.
        also_on_ebay=None if "eBay" in best_per_merchant else also_on_ebay,
    )
