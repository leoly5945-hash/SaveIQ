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

# Data-sufficiency gates. "Observations" means real price *changes*
# (``source_observations`` in the window, ``lifetime_observations`` over the whole
# tracked history) — not the densified daily point count.
_MIN_OBS_MEDIUM = 3
_MIN_OBS_HIGH = 8
_MIN_LIFETIME_MEDIUM = 15
_MIN_LIFETIME_HIGH = 40
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
    # Recent real observations, falling back to the densified point count only when
    # the provider gave us no change-count at all.
    recent = intel.source_observations
    if recent is None:
        recent = intel.total_points
    lifetime = intel.lifetime_observations or 0

    if intel.coverage_days >= _MIN_COVERAGE_DAYS_HIGH and (
        recent >= _MIN_OBS_HIGH or lifetime >= _MIN_LIFETIME_HIGH
    ):
        return Confidence.high
    if intel.coverage_days >= _MIN_COVERAGE_DAYS_MEDIUM and (
        recent >= _MIN_OBS_MEDIUM or lifetime >= _MIN_LIFETIME_MEDIUM
    ):
        return Confidence.medium
    return Confidence.low


def _money(cents: int, currency: str) -> str:
    return f"{cents / 100:.2f} {currency}"


def _resolve_band(intel: PriceIntelligence) -> tuple[int | None, int | None, int | None, int]:
    """90-day (avg, min, max, sample_count). Provider-computed stats win when present."""

    window_90 = intel.window(90)
    ps = intel.provider_stats or {}
    avg_90 = ps.get("avg90_cents") or (window_90.avg_cents if window_90 else None)
    min_90 = ps.get("min_cents") or (window_90.min_cents if window_90 else None)
    max_90 = ps.get("max_cents") or (window_90.max_cents if window_90 else None)
    samples = window_90.sample_count if window_90 else 0
    return avg_90, min_90, max_90, samples


def score_deal(
    effective_price: EffectivePrice,
    intelligence: PriceIntelligence,
) -> DealAssessment:
    """Score ``effective_price`` against ``intelligence`` and pick a verdict."""

    currency = effective_price.currency
    effective = effective_price.effective_cents
    reasons: list[str] = []
    confidence = _confidence(intelligence)

    avg_90, min_90, max_90, samples = _resolve_band(intelligence)

    # Nothing to judge against — a bare price with no usable band, or degenerate
    # (non-positive) numbers.
    if (
        avg_90 is None
        or min_90 is None
        or max_90 is None
        or avg_90 <= 0
        or effective <= 0
        or (samples < 3 and not intelligence.provider_stats)
    ):
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

    # The price has not moved across the whole window: there is no dip to wait for
    # and no discount to call out — it is simply the standing price.
    if min_90 == max_90:
        reasons.append(
            f"The price has held at {_money(min_90, currency)} for the last "
            f"90 days — no recent dips to wait for."
        )
        at_standing_price = effective <= round(min_90 * 1.02)
        return DealAssessment(
            verdict=Verdict.fair if at_standing_price else Verdict.wait,
            score=55 if at_standing_price else 40,
            confidence=confidence,
            reasons=reasons
            + (
                []
                if at_standing_price
                else [f"Effective {_money(effective, currency)} is above that standing price."]
            ),
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
