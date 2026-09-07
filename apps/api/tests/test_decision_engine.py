"""Unit tests for the deterministic decision engine (CP9–CP11).

Pure functions, synthetic price series, no provider / DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.providers.base import ProviderPrice, ProviderPriceHistory, ProviderPricePoint
from app.services.decision.assess import assess_from_provider
from app.services.decision.deal_score import Confidence, Verdict, score_deal
from app.services.decision.effective_price import (
    EffectivePriceComponent,
    compute_effective_price,
)
from app.services.decision.price_intelligence import summarize_points

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _pts(*pairs: tuple[float, int], kind: str = "amazon") -> list[ProviderPricePoint]:
    """`(days_ago, price_cents)` -> points."""

    return [
        ProviderPricePoint(observed_at=NOW - timedelta(days=d), price_cents=c, kind=kind)
        for d, c in pairs
    ]


# --- CP9: price intelligence -------------------------------------------------


def test_summarize_windows_and_stats() -> None:
    points = _pts(
        (120, 5000),
        (80, 4800),
        (40, 4600),
        (20, 4400),
        (5, 4200),
    )
    intel = summarize_points(points, currency="CAD", now=NOW)

    assert intel.series_kind == "amazon"
    assert intel.total_points == 5
    assert intel.current_cents == 4200  # last observation
    assert intel.all_time_min_cents == 4200
    assert intel.all_time_max_cents == 5000

    w7 = intel.window(7)
    assert w7 is not None and w7.sample_count == 1 and w7.min_cents == 4200
    w30 = intel.window(30)
    assert w30 is not None and w30.sample_count == 2  # 20d, 5d
    w90 = intel.window(90)
    assert w90 is not None and w90.sample_count == 4  # 80d, 40d, 20d, 5d
    assert w90.min_cents == 4200 and w90.max_cents == 4800
    w180 = intel.window(180)
    assert w180 is not None and w180.sample_count == 5


def test_percentile_and_all_time_low() -> None:
    points = _pts((80, 5000), (60, 4800), (40, 4600), (20, 4700), (2, 4300))
    intel = summarize_points(points, currency="CAD", current_cents=4300, now=NOW)
    # 4300 is the cheapest of the 90d window -> percentile ~0, all-time low.
    assert intel.current_percentile_90d == 0.0
    assert intel.is_all_time_low is True
    assert intel.times_this_low_90d == 1


def test_series_selection_prefers_requested_kind() -> None:
    mixed = _pts((10, 4000), kind="amazon") + _pts((10, 3900), (2, 3800), kind="buy_box")
    intel = summarize_points(mixed, currency="CAD", prefer_kind="buy_box", now=NOW)
    assert intel.series_kind == "buy_box"
    assert intel.total_points == 2
    assert intel.current_cents == 3800


def test_days_since_price_this_low() -> None:
    points = _pts((50, 4000), (30, 4500), (10, 4600), (1, 4000))
    intel = summarize_points(points, currency="CAD", current_cents=4000, now=NOW)
    # Last time it was <= 4000 before the latest point was 50 days ago.
    assert intel.days_since_price_this_low == 50


def test_summarize_handles_empty() -> None:
    intel = summarize_points([], currency="CAD", now=NOW)
    assert intel.total_points == 0
    assert intel.window(90) is not None
    assert intel.window(90).sample_count == 0  # type: ignore[union-attr]


# --- CP10: effective price -------------------------------------------------


def test_effective_price_adds_shipping() -> None:
    ep = compute_effective_price(4299, currency="CAD", shipping_cents=599)
    assert ep.effective_cents == 4898
    assert ep.base_price_cents == 4299
    assert [c.label for c in ep.components] == ["Shipping"]


def test_effective_price_free_shipping_no_component() -> None:
    ep = compute_effective_price(4299, currency="CAD", shipping_cents=0)
    assert ep.effective_cents == 4299
    assert ep.components == []


def test_effective_price_applies_signed_coupon() -> None:
    ep = compute_effective_price(
        5000,
        currency="CAD",
        shipping_cents=0,
        extra_components=[EffectivePriceComponent(label="Auto coupon", amount_cents=-500)],
    )
    assert ep.effective_cents == 4500
    assert ep.savings_vs_base_cents == 500


# --- CP11: deal score -----------------------------------------------------


def _intel_from(pairs: list[tuple[float, int]], current: int):
    return summarize_points(_pts(*pairs), currency="CAD", current_cents=current, now=NOW)


def test_verdict_buy_at_90d_low() -> None:
    pairs = [(float(d), 5000 - (d % 3) * 50) for d in range(1, 90, 2)]  # ~45 points, ~4900-5000
    intel = _intel_from(pairs, current=4300)
    ep = compute_effective_price(4300, currency="CAD")
    result = score_deal(ep, intel)
    assert result.verdict == Verdict.buy
    assert result.score >= 70
    assert result.confidence == Confidence.high
    assert any("below the 90-day average" in r for r in result.reasons)


def test_verdict_wait_when_well_above_average() -> None:
    pairs = [(float(d), 4000 + (d % 4) * 25) for d in range(1, 90, 2)]  # ~4000-4075
    intel = _intel_from(pairs, current=4800)  # ~19% above avg
    ep = compute_effective_price(4800, currency="CAD")
    result = score_deal(ep, intel)
    assert result.verdict == Verdict.wait
    assert result.score <= 40


def test_verdict_fair_in_the_middle() -> None:
    pairs = [(float(d), 4500 + (d % 5) * 40) for d in range(1, 90, 2)]  # ~4500-4660
    intel = _intel_from(pairs, current=4560)
    ep = compute_effective_price(4560, currency="CAD")
    result = score_deal(ep, intel)
    assert result.verdict == Verdict.fair


def test_verdict_unknown_when_history_is_thin() -> None:
    intel = _intel_from([(2.0, 4300), (1.0, 4200)], current=4200)
    ep = compute_effective_price(4200, currency="CAD")
    result = score_deal(ep, intel)
    assert result.verdict == Verdict.unknown
    assert result.score == 50
    assert result.confidence == Confidence.low


def test_flat_price_returns_fair_with_a_clear_reason() -> None:
    # A product whose price has not moved in 90 days: no dip to wait for.
    pairs = [(float(d), 4000) for d in range(1, 90, 3)]
    intel = _intel_from(pairs, current=4000)
    ep = compute_effective_price(4000, currency="CAD")
    result = score_deal(ep, intel)
    assert result.verdict == Verdict.fair
    assert any("held at" in r for r in result.reasons)


def test_flat_price_above_standing_price_says_wait() -> None:
    pairs = [(float(d), 4000) for d in range(1, 90, 3)]
    intel = _intel_from(pairs, current=4300)
    ep = compute_effective_price(4300, currency="CAD")
    result = score_deal(ep, intel)
    assert result.verdict == Verdict.wait


def test_provider_avg90_is_used_for_the_average() -> None:
    # The densified window averages ~45.50, but Keepa's own avg90 is 50.00 — the
    # "vs 90-day average" reason must cite the provider figure.
    pts = [
        ProviderPricePoint(
            observed_at=NOW - timedelta(days=d),
            price_cents=4600 if d % 2 else 4500,
            kind="a",
        )
        for d in range(0, 90)
    ]
    intel = summarize_points(
        pts,
        currency="CAD",
        current_cents=4300,
        now=NOW,
        source_observations=5,
        lifetime_observations=50,
        provider_stats={"avg90_cents": 5000, "min_cents": 999, "max_cents": 9999},
    )
    ep = compute_effective_price(4300, currency="CAD")
    result = score_deal(ep, intel)
    assert result.verdict != Verdict.unknown
    assert any("50.00 CAD" in r for r in result.reasons)
    # Lifetime min/max from the provider land on all_time_*, not the 90-day band.
    assert intel.all_time_min_cents == 999
    assert intel.all_time_max_cents == 9999


def test_confidence_uses_lifetime_observations() -> None:
    intel = summarize_points(
        [
            ProviderPricePoint(observed_at=NOW - timedelta(days=d), price_cents=4000 + d, kind="a")
            for d in range(0, 90)
        ],
        currency="CAD",
        current_cents=4000,
        now=NOW,
        source_observations=0,
        lifetime_observations=60,
    )
    ep = compute_effective_price(4000, currency="CAD")
    result = score_deal(ep, intel)
    # 0 recent changes but a long tracked history + 90d coverage -> not "low".
    assert result.confidence in {Confidence.medium, Confidence.high}


def test_score_has_no_commission_input() -> None:
    # Guard against a future regression: score_deal takes exactly the price and
    # the intelligence — nothing merchant/payout related.
    import inspect

    params = list(inspect.signature(score_deal).parameters)
    assert params == ["effective_price", "intelligence"]


# --- orchestrator --------------------------------------------------------


def test_assess_from_provider_end_to_end() -> None:
    points = _pts(*[(float(d), 5000 - (d % 3) * 40) for d in range(1, 90, 2)], kind="buy_box")
    history = ProviderPriceHistory(
        provider="keepa",
        provider_product_id="B09VPHVT9Z",
        currency="CAD",
        points=points,
    )
    price = ProviderPrice(
        provider="keepa",
        provider_product_id="B09VPHVT9Z",
        price_cents=4300,
        currency="CAD",
        observed_at=NOW,
        source="keepa:buy_box",
    )
    result = assess_from_provider(price, history, now=NOW)
    assert result is not None
    assert result.intelligence.series_kind == "buy_box"
    assert result.effective_price.effective_cents == 4300
    assert result.verdict in {Verdict.buy, Verdict.fair}


def test_assess_from_provider_returns_none_without_price() -> None:
    history = ProviderPriceHistory(
        provider="keepa", provider_product_id="X", currency="CAD", points=[]
    )
    price = ProviderPrice(
        provider="keepa",
        provider_product_id="X",
        price_cents=None,
        currency="CAD",
        observed_at=NOW,
        source="keepa:unknown",
    )
    assert assess_from_provider(price, history, now=NOW) is None
