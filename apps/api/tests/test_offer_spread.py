"""Summarising the Amazon offer list into a buy-box spread."""

from __future__ import annotations

from datetime import UTC, datetime

from app.providers.base import ProviderOffer
from app.services.decision.offer_spread import summarize_amazon_offers

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def _offer(
    cents: int, *, condition: str, buy_box: bool = False, fba: bool = False
) -> ProviderOffer:
    return ProviderOffer(
        provider="keepa",
        provider_product_id="B0TEST",
        merchant="seller",
        price_cents=cents,
        shipping_cents=0,
        currency="CAD",
        condition=condition,
        is_buy_box=buy_box,
        observed_at=NOW,
        metadata={"is_fba": fba},
    )


def test_none_when_no_buy_box_price() -> None:
    assert summarize_amazon_offers([], buy_box_cents=None, currency="CAD") is None
    assert summarize_amazon_offers([], buy_box_cents=0, currency="CAD") is None


def test_none_when_only_the_buy_box() -> None:
    offers = [_offer(13000, condition="new", buy_box=True)]
    assert summarize_amazon_offers(offers, buy_box_cents=13000, currency="CAD") is None


def test_cheaper_third_party_new_becomes_a_tier() -> None:
    offers = [
        _offer(13000, condition="new", buy_box=True),
        _offer(11800, condition="new", fba=True),
        _offer(12950, condition="new"),  # basically the buy box — not news
    ]
    spread = summarize_amazon_offers(offers, buy_box_cents=13000, currency="CAD")
    assert spread is not None
    new_tier = next(t for t in spread.tiers if t.condition == "new")
    assert new_tier.lowest_total_cents == 11800
    assert new_tier.offer_count == 1  # the 129.50 echo is excluded
    assert new_tier.fba_available is True
    assert spread.lowest_overall_cents == 11800
    assert spread.savings_vs_buy_box_cents == 1200


def test_used_tier_and_refurbished_bucket_together() -> None:
    offers = [
        _offer(13000, condition="new", buy_box=True),
        _offer(9900, condition="used"),
        _offer(10500, condition="refurbished"),
    ]
    spread = summarize_amazon_offers(offers, buy_box_cents=13000, currency="CAD")
    assert spread is not None
    used = next(t for t in spread.tiers if t.condition == "used")
    assert used.lowest_total_cents == 9900
    assert used.offer_count == 2
    assert spread.savings_vs_buy_box_cents == 3100


def test_collectible_and_unknown_conditions_are_ignored() -> None:
    offers = [
        _offer(13000, condition="new", buy_box=True),
        _offer(8000, condition="collectible"),
        _offer(8500, condition="unknown"),
    ]
    assert summarize_amazon_offers(offers, buy_box_cents=13000, currency="CAD") is None


def test_shipping_counts_toward_the_total() -> None:
    o = ProviderOffer(
        provider="keepa",
        provider_product_id="B0TEST",
        merchant="s",
        price_cents=11000,
        shipping_cents=2500,
        currency="CAD",
        condition="new",
        observed_at=NOW,
    )
    spread = summarize_amazon_offers([o], buy_box_cents=13000, currency="CAD")
    # 110 + 25 shipping = 135 total, above the 130 buy box -> not shown
    assert spread is None
