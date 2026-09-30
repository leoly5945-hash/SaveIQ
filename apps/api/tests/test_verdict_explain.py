"""Plain-English verdict explanation + fake-discount checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.decision.deal_score import Confidence, DealAssessment, Verdict
from app.services.decision.effective_price import EffectivePrice
from app.services.decision.explain import explain_verdict
from app.services.decision.price_intelligence import PriceIntelligence, WindowStat


def _assessment(
    verdict: Verdict,
    now: int,
    *,
    low: int = 4000,
    high: int = 6000,
    avg: int = 5000,
    median90: int | None = None,
    max30: int | None = None,
) -> DealAssessment:
    windows = {
        90: WindowStat(
            days=90,
            sample_count=90,
            min_cents=low,
            max_cents=high,
            avg_cents=avg,
            median_cents=median90 if median90 is not None else avg,
        ),
        30: WindowStat(
            days=30,
            sample_count=30,
            min_cents=low,
            max_cents=max30 if max30 is not None else high,
            avg_cents=avg,
            median_cents=avg,
        ),
    }
    intel = PriceIntelligence(
        currency="CAD",
        series_kind="buy_box",
        total_points=90,
        current_cents=now,
        windows=windows,
        provider_stats={"avg90_cents": avg},
    )
    return DealAssessment(
        verdict=verdict,
        score=50,
        confidence=Confidence.high,
        reasons=[],
        effective_price=EffectivePrice(base_price_cents=now, effective_cents=now, currency="CAD"),
        intelligence=intel,
    )


def test_buy_at_the_90_day_low_says_so() -> None:
    e = explain_verdict(_assessment(Verdict.buy, 4000))
    assert e.headline == "This is the lowest price in the last 90 days."
    assert e.position is not None and e.position.position == 0.0


def test_buy_near_the_low_gives_the_gap() -> None:
    e = explain_verdict(_assessment(Verdict.buy, 4100))
    assert "Within 2% of its lowest price in the last 90 days ($40.00)" in e.headline


def test_wait_at_the_90_day_high() -> None:
    e = explain_verdict(_assessment(Verdict.wait, 6000))
    assert e.headline.startswith("This is at or near its highest price of the last 90 days.")
    assert "as little as $40.00" in e.headline
    assert e.position is not None and e.position.position == 1.0


def test_wait_above_usual_price() -> None:
    e = explain_verdict(_assessment(Verdict.wait, 5800))
    assert e.headline.startswith("About 16% above its usual price of $50.00.")


def test_fair_around_usual_price() -> None:
    e = explain_verdict(_assessment(Verdict.fair, 5000))
    assert e.headline.startswith("Around its usual price of $50.00.")
    assert "$40.00 to $60.00" in e.headline


def test_unknown_has_no_position() -> None:
    e = explain_verdict(_assessment(Verdict.unknown, 5000))
    assert e.headline.startswith("Not enough price history yet")
    assert e.position is None
    assert e.discount_checks == []


def test_inflated_list_price_is_flagged() -> None:
    # Sells at $40-$60, sits at $45 "-44%" off a $80 list price.
    e = explain_verdict(_assessment(Verdict.fair, 4500), list_price_cents=8000)
    [check] = [c for c in e.discount_checks if c.kind == "inflated_list_price"]
    assert check.warning is True
    assert "$80.00" in check.message and "highest: $60.00" in check.message
    assert "−44%" in check.message


def test_realistic_list_price_is_confirmed() -> None:
    e = explain_verdict(_assessment(Verdict.buy, 4000), list_price_cents=5400)
    [check] = e.discount_checks
    assert check.kind == "list_price_ok" and check.warning is False


def test_list_price_at_or_below_today_is_ignored() -> None:
    e = explain_verdict(_assessment(Verdict.fair, 5000), list_price_cents=5000)
    assert e.discount_checks == []


_NOW = datetime(2026, 9, 29, tzinfo=UTC)


def _history(earlier: int, recent_peak: int, today: int) -> list[tuple[datetime, int]]:
    """90 daily points: 60 days at `earlier`, a spike to `recent_peak`, then `today`."""
    points = [(_NOW - timedelta(days=d), earlier) for d in range(89, 29, -1)]
    points += [(_NOW - timedelta(days=d), recent_peak) for d in range(29, 5, -1)]
    points += [(_NOW - timedelta(days=d), today) for d in range(5, -1, -1)]
    return points


def test_raise_then_drop_is_flagged() -> None:
    # Usually $50, pushed to a new high of $65 this month, now "down" to $50.
    e = explain_verdict(
        _assessment(Verdict.fair, 5000, high=6500, median90=5000, max30=6500),
        history=_history(5000, 6500, 5000),
    )
    [check] = [c for c in e.discount_checks if c.kind == "raise_then_drop"]
    assert check.warning is True
    assert "$65.00" in check.message and "$50.00" in check.message


def test_a_real_drop_below_usual_is_not_called_a_hike() -> None:
    e = explain_verdict(
        _assessment(Verdict.buy, 4000, high=6500, median90=5000, max30=6500),
        history=_history(5000, 6500, 4000),
    )
    assert all(c.kind != "raise_then_drop" for c in e.discount_checks)


def test_normal_swings_are_not_called_a_hike() -> None:
    # It has sold at $60 before; reaching $60 again this month isn't a new high.
    history = [(_NOW - timedelta(days=d), 6000 if d % 20 < 5 else 4500) for d in range(89, 0, -1)]
    history.append((_NOW, 5000))
    e = explain_verdict(_assessment(Verdict.fair, 5000), history=history)
    assert all(c.kind != "raise_then_drop" for c in e.discount_checks)


def test_no_history_skips_the_hike_check() -> None:
    e = explain_verdict(_assessment(Verdict.fair, 5000, high=6500, median90=5000, max30=6500))
    assert all(c.kind != "raise_then_drop" for c in e.discount_checks)


def test_fair_well_below_usual_gives_the_real_gap() -> None:
    # Nalgene on prod: $16.87 vs a (skewed) usual $28.82 is not "a little" below.
    e = explain_verdict(_assessment(Verdict.fair, 1687, low=1568, high=4794, avg=2882))
    assert e.headline.startswith("41% below its usual price of $28.82")
    assert "90-day low of $15.68" in e.headline


def test_fair_slightly_below_usual_says_a_little() -> None:
    e = explain_verdict(_assessment(Verdict.fair, 4850))
    assert e.headline.startswith("A little below its usual price of $50.00")


def test_fair_above_usual() -> None:
    e = explain_verdict(_assessment(Verdict.fair, 5500))
    assert e.headline.startswith("About 10% above its usual price of $50.00")


def test_near_flat_range_hides_the_bar() -> None:
    # Energizer on prod: $14.97-$14.98 for 90 days; one cent must not read as "highest".
    e = explain_verdict(_assessment(Verdict.fair, 1498, low=1497, high=1498, avg=1497))
    assert e.position is None
    assert e.headline.startswith("The price has barely moved in 90 days ($14.97 to $14.98)")


def test_exactly_flat_range() -> None:
    e = explain_verdict(_assessment(Verdict.fair, 2000, low=2000, high=2000, avg=2000))
    assert e.position is None
    assert e.headline.startswith("The price has held at $20.00 for the last 90 days")


def test_list_price_at_a_brief_peak_is_not_called_genuine() -> None:
    # iPhone 16e (renewed) on prod: usual ~$606, one spike to $673.93, list $673.99.
    e = explain_verdict(
        _assessment(Verdict.fair, 60299, low=58752, high=67393, avg=60619),
        list_price_cents=67399,
    )
    [check] = e.discount_checks
    assert check.kind == "list_price_at_peak"
    assert check.warning is True
    assert "usually sells for about $606.19" in check.message
    assert "−11%" in check.message
