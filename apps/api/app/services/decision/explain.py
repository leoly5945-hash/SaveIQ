"""Plain-English "why" behind a verdict, plus a check on whether a discount is real.

Shoppers get one short sentence that ties the verdict to the price history
("the highest price in 90 days — it has sold for $X"), where today's price sits
between the 90-day low and high, and warnings when a deal looks better than it
is:

* **Inflated list price** — the struck-through "List Price" a "-N%" badge is
  measured from is higher than anything the product has actually sold for
  lately, so the percentage overstates the saving.
* **List price at the peak** — the list price matches a brief 90-day high but
  sits well above what it usually sells for, so the "-N%" looks bigger than
  the everyday saving. Only a list price near the usual price is called
  genuine.
* **Raise-then-drop** — the price was pushed to a *new* high in the last 30
  days (above anything in the 60 days before), so today's "drop" mostly undoes
  that rise and the price is still around its usual level. A product that just
  swings inside its normal range is not flagged.

Everything is computed from the same 90-day band the verdict uses, so the
explanation can never contradict the verdict.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.services.decision.deal_score import DealAssessment, Verdict, _resolve_band

# A 90-day range narrower than this (relative to the low) counts as flat: a
# one-cent wobble must not put the "today" marker at the red "highest" end.
_FLAT_RANGE_RATIO = 0.02
# A list price this far above the 90-day high is not a price it really sells at.
_INFLATED_LIST_RATIO = 1.10
# A list price within this of the usual price is a fair baseline for a discount.
_USUAL_LIST_RATIO = 1.10
# A 30-day peak this far above the 90-day median counts as a price hike...
_HIKE_RATIO = 1.20
# ...but only if it is also this far above the peak of the 60 days before it.
_NEW_HIGH_RATIO = 1.10


class PricePosition(BaseModel):
    low_cents: int
    high_cents: int
    avg_cents: int | None
    current_cents: int
    # 0 = at the 90-day low, 1 = at the 90-day high (clamped).
    position: float


class DiscountCheck(BaseModel):
    kind: Literal["inflated_list_price", "list_price_at_peak", "raise_then_drop", "list_price_ok"]
    warning: bool
    message: str


class VerdictExplanation(BaseModel):
    headline: str
    position: PricePosition | None = None
    discount_checks: list[DiscountCheck] = Field(default_factory=list)


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _pct(numerator: float, denominator: float) -> int:
    return round(numerator / denominator * 100) if denominator else 0


def explain_verdict(
    assessment: DealAssessment,
    *,
    list_price_cents: int | None = None,
    history: Sequence[tuple[datetime, int]] | None = None,
) -> VerdictExplanation:
    """``history`` is the daily (observed_at, price_cents) series the verdict was
    built from; without it the raise-then-drop check is skipped."""
    intel = assessment.intelligence
    now = assessment.effective_price.effective_cents
    avg, low, high, _samples = _resolve_band(intel)
    verdict = assessment.verdict

    if verdict == Verdict.unknown or low is None or high is None or now <= 0:
        return VerdictExplanation(
            headline=(
                "Not enough price history yet to judge this price. "
                "Set an alert and we'll watch it for you."
            )
        )

    flat = high - low <= low * _FLAT_RANGE_RATIO
    position = (
        None
        if flat
        else PricePosition(
            low_cents=low,
            high_cents=high,
            avg_cents=avg,
            current_cents=now,
            position=max(0.0, min(1.0, (now - low) / (high - low))),
        )
    )
    usual = avg if avg else None

    if flat:
        headline = (
            (
                f"The price has held at {_money(low)} for the last 90 days, "
                "so there's no dip to wait for."
                if high == low
                else f"The price has barely moved in 90 days ({_money(low)} to "
                f"{_money(high)}), so there's no dip to wait for."
            )
            if now <= round(high * 1.02)
            else f"It's above the {_money(low)}–{_money(high)} it has sold for over the "
            "last 90 days."
        )
    elif verdict == Verdict.buy:
        headline = (
            "This is the lowest price in the last 90 days."
            if now <= low
            else f"Within {_pct(now - low, low)}% of its lowest price in the last "
            f"90 days ({_money(low)})."
        )
    elif verdict == Verdict.wait:
        if now >= round(high * 0.98):
            headline = (
                "This is at or near its highest price of the last 90 days. "
                f"It has sold for as little as {_money(low)}."
            )
        elif usual:
            headline = (
                f"About {_pct(now - usual, usual)}% above its usual price of "
                f"{_money(usual)}. It has sold for as little as {_money(low)} "
                "in the last 90 days."
            )
        else:
            headline = f"Well above its 90-day low of {_money(low)}."
    else:  # fair
        below = _pct(usual - now, usual) if usual else 0
        if usual and below >= 10:
            headline = (
                f"{below}% below its usual price of {_money(usual)}, though not at "
                f"its 90-day low of {_money(low)}."
            )
        elif usual and now < usual * 0.98:
            headline = (
                f"A little below its usual price of {_money(usual)}, but not near "
                f"its 90-day low of {_money(low)}."
            )
        elif usual and now > usual * 1.05:
            headline = (
                f"About {_pct(now - usual, usual)}% above its usual price of "
                f"{_money(usual)}, but below its 90-day high of {_money(high)}."
            )
        elif usual:
            headline = (
                f"Around its usual price of {_money(usual)}. Over the last 90 days "
                f"it ranged from {_money(low)} to {_money(high)}."
            )
        else:
            headline = f"In the middle of its 90-day range of {_money(low)} to {_money(high)}."

    return VerdictExplanation(
        headline=headline,
        position=position,
        discount_checks=_discount_checks(
            assessment,
            now=now,
            high=high,
            usual=usual,
            list_price_cents=list_price_cents,
            history=history,
        ),
    )


def _discount_checks(
    assessment: DealAssessment,
    *,
    now: int,
    high: int,
    usual: int | None,
    list_price_cents: int | None,
    history: Sequence[tuple[datetime, int]] | None,
) -> list[DiscountCheck]:
    checks: list[DiscountCheck] = []

    # Only meaningful when the list price implies a discount off today's price.
    if list_price_cents and list_price_cents > round(now * 1.02):
        off = _pct(list_price_cents - now, list_price_cents)
        if list_price_cents > high * _INFLATED_LIST_RATIO:
            compare = f" Compare with its usual price of {_money(usual)} instead." if usual else ""
            checks.append(
                DiscountCheck(
                    kind="inflated_list_price",
                    warning=True,
                    message=(
                        f"The “List Price” of {_money(list_price_cents)} is higher than "
                        "any price we've seen it sell for on Amazon.ca in the last 90 "
                        f"days (highest: {_money(high)}), so a “−{off}%” deal measured "
                        f"from it overstates the saving.{compare}"
                    ),
                )
            )
        elif usual and list_price_cents > usual * _USUAL_LIST_RATIO:
            checks.append(
                DiscountCheck(
                    kind="list_price_at_peak",
                    warning=True,
                    message=(
                        f"The “List Price” of {_money(list_price_cents)} matches its "
                        f"highest price in the last 90 days, but it usually sells for "
                        f"about {_money(usual)}, so a “−{off}%” measured from it looks "
                        "bigger than the everyday saving."
                    ),
                )
            )
        else:
            checks.append(
                DiscountCheck(
                    kind="list_price_ok",
                    warning=False,
                    message=(
                        f"The “List Price” of {_money(list_price_cents)} is in line with "
                        "prices it has actually sold for recently, so the discount "
                        "shown from it is genuine."
                    ),
                )
            )

    hike = _recent_new_high(history)
    w90 = assessment.intelligence.window(90)
    median = w90.median_cents if w90 else None
    if (
        hike is not None
        and median
        and hike >= median * _HIKE_RATIO
        and now >= median * 0.97
        and now < hike * 0.95
    ):
        peak = hike
        checks.append(
            DiscountCheck(
                kind="raise_then_drop",
                warning=True,
                message=(
                    f"The price went up to {_money(peak)} in the last 30 days, so "
                    "today's lower price mostly undoes that rise. It's still around "
                    f"its usual {_money(median)}, not a real discount."
                ),
            )
        )
    return checks


def _recent_new_high(history: Sequence[tuple[datetime, int]] | None) -> int | None:
    """The last-30-day peak, if it beats the peak of the 60 days before it."""

    if not history:
        return None
    latest = max(t for t, _ in history)
    recent_from = latest - timedelta(days=30)
    earlier_from = latest - timedelta(days=90)
    recent = [c for t, c in history if t > recent_from]
    earlier = [c for t, c in history if earlier_from < t <= recent_from]
    if not recent or not earlier:
        return None
    peak = max(recent)
    return peak if peak >= max(earlier) * _NEW_HIGH_RATIO else None
