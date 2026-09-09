"""Tests for CP7 cross-merchant product matching."""

from __future__ import annotations

from datetime import UTC, datetime

from app.providers.base import ProviderOffer
from app.services.decision.matching import build_comparison, score_candidate

NOW = datetime(2026, 9, 9, tzinfo=UTC)
REF_TITLE = "Anker SOLIX S2000 Portable Power Station, 2010Wh, 1500W Solar Generator"
REF_BRAND = "Anker"
REF_CENTS = 94900  # $949


def _offer(merchant: str, cents: int, title: str, url: str = "https://x") -> ProviderOffer:
    return ProviderOffer(
        provider="dataforseo",
        provider_product_id=REF_TITLE,
        merchant=merchant,
        price_cents=cents,
        currency="CAD",
        url=url,
        observed_at=NOW,
        metadata={"title": title},
    )


# --- score_candidate ----------------------------------------------------


def test_scores_a_clear_match_high() -> None:
    s = score_candidate(
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        candidate_title="Anker SOLIX S2000 Power Station 2010Wh Solar Generator",
        candidate_price_cents=89900,
    )
    assert s >= 0.7


def test_rejects_wrong_brand() -> None:
    assert (
        score_candidate(
            reference_title=REF_TITLE,
            reference_brand=REF_BRAND,
            reference_price_cents=REF_CENTS,
            candidate_title="Jackery Explorer 2000 Portable Power Station Solar Generator",
            candidate_price_cents=95000,
        )
        == 0.0
    )


def test_rejects_accessory() -> None:
    assert (
        score_candidate(
            reference_title=REF_TITLE,
            reference_brand=REF_BRAND,
            reference_price_cents=REF_CENTS,
            candidate_title="Carrying Case for Anker SOLIX S2000 Power Station",
            candidate_price_cents=6900,
        )
        == 0.0
    )


def test_rejects_price_far_out_of_band() -> None:
    assert (
        score_candidate(
            reference_title=REF_TITLE,
            reference_brand=REF_BRAND,
            reference_price_cents=REF_CENTS,
            candidate_title="Anker SOLIX S2000 Power Station bundle with extra battery",
            candidate_price_cents=250000,
        )
        == 0.0
    )


# --- build_comparison -------------------------------------------------


def test_build_comparison_ranks_and_flags_cheaper() -> None:
    candidates = [
        _offer("Best Buy Canada", 96999, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
        _offer("Walmart Canada", 89900, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
        _offer("Some Random Store", 4999, "Phone case compatible with Anker"),  # accessory
        _offer("Jackery Store", 92000, "Jackery Explorer 2000 Solar Generator"),  # wrong product
        _offer("Amazon.ca", 94900, "Anker SOLIX S2000 Portable Power Station"),  # self — skipped
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert [o.merchant for o in comp.offers] == ["Walmart Canada", "Best Buy Canada"]
    assert comp.offers[0].price_cents == 89900
    assert comp.cheapest is not None and comp.cheapest.merchant == "Walmart Canada"


def test_build_comparison_no_cheaper_when_amazon_wins() -> None:
    candidates = [
        _offer("Best Buy Canada", 99900, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert len(comp.offers) == 1
    assert comp.cheapest is None  # Amazon's price is still the best


def test_build_comparison_skips_amazon_family_echo() -> None:
    candidates = [
        _offer("Amazon", 88000, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
        _offer("Amazon.com", 87000, "Anker SOLIX S2000 Portable Power Station"),
        _offer("Amazon Warehouse", 86000, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
        _offer("Best Buy Canada", 96999, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert [o.merchant for o in comp.offers] == ["Best Buy Canada"]
    assert comp.cheapest is None


def test_build_comparison_lists_weak_match_but_does_not_flag_cheaper() -> None:
    # cheaper price, but a sparse title -> above the inclusion bar, below the
    # "cheaper at X" bar: shown in the list, not flagged.
    candidates = [_offer("Staples Canada", 80000, "Anker SOLIX portable")]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert len(comp.offers) == 1
    assert 0.55 <= comp.offers[0].match_confidence < 0.65
    assert comp.cheapest is None


def test_build_comparison_dedupes_merchant_keeps_cheapest() -> None:
    candidates = [
        _offer("Walmart Canada", 91900, "Anker SOLIX S2000 Power Station 2010Wh"),
        _offer("Walmart Canada", 88900, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert len(comp.offers) == 1
    assert comp.offers[0].price_cents == 88900
