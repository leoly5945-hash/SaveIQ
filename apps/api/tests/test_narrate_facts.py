from types import SimpleNamespace

from app.services.decision.deal_score import Confidence, Verdict
from app.services.decision.offer_spread import AmazonOfferSpread, SpreadTier
from app.services.discovery.narrate import _SYSTEM, _facts


def _tier(condition: str, cents: int) -> SpreadTier:
    return SpreadTier(
        condition=condition, lowest_total_cents=cents, offer_count=2, fba_available=False
    )


def _result(verdict: Verdict, spread: AmazonOfferSpread | None = None):
    assessment = SimpleNamespace(
        verdict=verdict,
        confidence=Confidence.high,
        effective_price=SimpleNamespace(effective_cents=128699),
        reasons=["About 5% above its usual price"],
    )
    return SimpleNamespace(
        title="MacBook Pro 14 (Renewed)",
        provider_product_id="B000000000",
        currency="CAD",
        assessment=assessment,
        spread=spread,
        comparison=None,
    )


def test_fair_advice_forbids_telling_the_shopper_to_wait():
    facts = _facts(_result(Verdict.fair))
    assert "Advice:" in facts
    assert "Do not tell them to hold off or wait" in facts
    assert "never contradict" in _SYSTEM


def test_wait_advice_says_wait():
    assert "Say to wait" in _facts(_result(Verdict.wait))


def test_cheapest_used_seller_is_labelled_used():
    spread = AmazonOfferSpread(
        buy_box_cents=114900,
        currency="CAD",
        lowest_overall_cents=98000,
        savings_vs_buy_box_cents=16900,
        tiers=[
            _tier("new", 112000),
            _tier("used", 98000),
        ],
    )
    assert "980.00 CAD (used / renewed)" in _facts(_result(Verdict.fair, spread))


def test_cheapest_new_seller_is_not_labelled_used():
    spread = AmazonOfferSpread(
        buy_box_cents=114900,
        currency="CAD",
        lowest_overall_cents=112000,
        savings_vs_buy_box_cents=2900,
        tiers=[_tier("new", 112000)],
    )
    assert "used / renewed" not in _facts(_result(Verdict.fair, spread))
