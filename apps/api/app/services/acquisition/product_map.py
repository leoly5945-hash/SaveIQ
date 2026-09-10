"""Map a resolved product (Amazon category text + brand + title) onto the
acquisition taxonomy so :func:`compose_options` can run on it.

Keyword matching, deliberately loose. Anything unrecognised falls through to
``general`` — which only the "*" programs (buy outright, Amazon Renewed) apply
to, so the advisor still answers.
"""

from __future__ import annotations

from app.services.acquisition.composer import ProductContext

# (keywords, our category, tier). First hit on the category text or title wins.
_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("cell phone", "smartphone", "iphone", "galaxy s", "pixel phone", "unlocked phone"),
        "smartphone",
        "flagship",
    ),
    (
        ("cellular smartwatch", "apple watch", "watch (gps + cellular)", "lte smartwatch"),
        "cellular_watch",
        "flagship",
    ),
    (("laptop", "notebook computer", "macbook", "chromebook", "ultrabook"), "laptop", "flagship"),
    (("ipad", "android tablet", "tablet computer", "galaxy tab"), "tablet", "flagship"),
    (("television", "oled tv", "qled tv", "4k tv", "smart tv", "led tv"), "television", "flagship"),
    (("home theater", "soundbar", "av receiver", "home theatre"), "home_theatre", "flagship"),
    (
        ("headphone", "earbud", "earphone", "headset", "over-ear", "in-ear"),
        "headphones",
        "flagship",
    ),
    (
        (
            "refrigerator",
            "washing machine",
            "clothes dryer",
            "dishwasher",
            "freezer",
            "range hood",
            "cooktop",
            "wall oven",
            "washer",
        ),
        "major_appliance",
        "flagship",
    ),
    (
        (
            "sofa",
            "sectional",
            "couch",
            "mattress",
            "bed frame",
            "dining table",
            "dresser",
            "bookcase",
        ),
        "furniture",
        "flagship",
    ),
]

_MIDRANGE_HINTS = ("budget", "essential", "lite", "se ", " a1", " a2", "fan edition", " fe")


def infer_product_context(
    *,
    price_cents: int,
    category: str | None,
    brand: str | None,
    title: str | None,
    carrier_eligible: bool | None = None,
) -> ProductContext:
    hay = " ".join(x.lower() for x in (category or "", title or "") if x)
    resolved_category = "general"
    tier = "flagship"
    for keywords, cat, default_tier in _RULES:
        if any(k in hay for k in keywords):
            resolved_category, tier = cat, default_tier
            break
    if resolved_category == "smartphone" and any(h in hay for h in _MIDRANGE_HINTS):
        tier = "midrange"
    return ProductContext(
        retail_price_cents=price_cents,
        category=resolved_category,
        brand=(brand or "").strip().lower() or None,
        tier=tier,
        carrier_eligible=carrier_eligible,
    )
