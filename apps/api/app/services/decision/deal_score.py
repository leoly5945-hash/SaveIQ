"""CP11 — deterministic deal score and BUY / WAIT / FAIR verdict.

Given an effective price (CP10) and price intelligence (CP9), produce a
transparent 0–100 score and a verdict. **Deterministic and rules-only** — no ML,
no learned weights, and no input for merchant commission or affiliate payout. A
higher-paying merchant can never earn a better score; there is nowhere in this
function to express that.

Every rule that fires appends a plain-language reason, so the UI can show *why*
a verdict was reached.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.services.decision.effective_price import EffectivePrice
from app.services.decision.price_intelligence import PriceIntelligence

# Data-sufficiency gates. Keepa records a point on every price *change*, not
# daily, so coverage (how long we've watched) matters more than raw point count;
# point count is only a floor to reject near-empty series.
_MIN_POINTS_MEDIUM = 4
_MIN_POINTS_HIGH = 8
_MIN_COVERAGE_DAYS_MEDIUM = 21
_MIN_COVERAGE_DAYS_HIGH = 60

# Verdict thresholds (see module docstring / docs for the rationale).
_BUY_SCORE = 70
_WAIT_SCORE = 36
_BUY_NEAR_LOW_RATIO = 1.05  # within 5% of the 90-day low
_WAIT_PREMIUM_RATIO = 1.15  # 15%+ above the 90-day average


class Verdict(StrEnum):
    buy = "BUY"
    fair = "FAIR"
    wait = "WAIT"
    unknown = "UNKNOWN"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class DealAssessment(BaseModel):
    verdict: Verdict
    score: int  # 0–100, higher = better time to buy
    confidence: Confidence
    reasons: list[str] = Field(default_factory=list)
    effective_price: EffectivePrice
    intelligence: PriceIntelligence


def _confidence(intel: PriceIntelligence) -> Confidence:
    if intel.total_points >= _MIN_POINTS_HIGH and intel.coverage_days >= _MIN_COVERAGE_DAYS_HIGH:
        return Confidence.high
    if (
        intel.total_points >= _MIN_POINTS_MEDIUM
        and intel.coverage_days >= _MIN_COVERAGE_DAYS_MEDIUM
    ):
        return Confidence.medium
    return Confidence.low


def _money(cents: int, currency: str) -> str:
    return f"{cents / 100:.2f} {currency}"


def score_deal(
    effective_price: EffectivePrice,
    intelligence: PriceIntelligence,
) -> DealAssessment:
    """Score ``effective_price`` against ``intelligence`` and pick a verdict."""

    currency = effective_price.currency
    effective = effective_price.effective_cents
    reasons: list[str] = []
    confidence = _confidence(intelligence)

    window_90 = intelligence.window(90)
    avg_90 = window_90.avg_cents if window_90 else None
    min_90 = window_90.min_cents if window_90 else None
    max_90 = window_90.max_cents if window_90 else None

    # Not enough history to judge against — report the price, don't pretend.
    if avg_90 is None or min_90 is None or (window_90 and window_90.sample_count < 3):
        reasons.append(
            "Not enough price history yet to judge this price — we'll know more "
            "as we keep tracking it."
        )
        return DealAssessment(
            verdict=Verdict.unknown,
            score=50,
            confidence=Confidence.low,
            reasons=reasons,
            effective_price=effective_price,
            intelligence=intelligence,
        )

    # --- score -----------------------------------------------------------------
    # Start neutral; move on how the effective price compares to the 90-day average.
    discount_vs_avg = (avg_90 - effective) / avg_90
    score = 50.0 + 250.0 * discount_vs_avg

    if discount_vs_avg >= 0.02:
        reasons.append(
            f"Effective {_money(effective, currency)} is "
            f"{discount_vs_avg * 100:.0f}% below the 90-day average of "
            f"{_money(avg_90, currency)}."
        )
    elif discount_vs_avg <= -0.02:
        reasons.append(
            f"Effective {_money(effective, currency)} is "
            f"{-discount_vs_avg * 100:.0f}% above the 90-day average of "
            f"{_money(avg_90, currency)}."
        )
    else:
        reasons.append(
            f"Effective {_money(effective, currency)} is about the 90-day "
            f"average ({_money(avg_90, currency)})."
        )

    near_90_low = effective <= round(min_90 * 1.02)
    if near_90_low:
        score += 15
        reasons.append(f"At or near the 90-day low of {_money(min_90, currency)}.")

    if intelligence.is_all_time_low and intelligence.all_time_min_cents is not None:
        score += 10
        reasons.append(
            f"This is the lowest price we've recorded "
            f"({_money(intelligence.all_time_min_cents, currency)})."
        )

    if max_90 is not None and effective >= round(max_90 * 0.98):
        score -= 15
        reasons.append(f"At or near the 90-day high of {_money(max_90, currency)}.")

    if intelligence.times_this_low_90d >= 3:
        reasons.append(
            f"The price has been this low {intelligence.times_this_low_90d} times "
            f"in the last 90 days — it comes back."
        )
    elif (
        intelligence.days_since_price_this_low is not None
        and intelligence.days_since_price_this_low >= 60
    ):
        reasons.append(f"It hasn't been this low in {intelligence.days_since_price_this_low} days.")

    score_int = max(0, min(100, round(score)))

    # --- verdict -------------------------------------------------------------
    premium_vs_avg = (effective - avg_90) / avg_90
    if score_int >= _BUY_SCORE and effective <= round(min_90 * _BUY_NEAR_LOW_RATIO):
        verdict = Verdict.buy
    elif score_int <= _WAIT_SCORE or premium_vs_avg >= (_WAIT_PREMIUM_RATIO - 1.0):
        verdict = Verdict.wait
        if premium_vs_avg >= (_WAIT_PREMIUM_RATIO - 1.0):
            reasons.append("It has traded well below this recently — worth waiting for a dip.")
    else:
        verdict = Verdict.fair

    return DealAssessment(
        verdict=verdict,
        score=score_int,
        confidence=confidence,
        reasons=reasons,
        effective_price=effective_price,
        intelligence=intelligence,
    )
