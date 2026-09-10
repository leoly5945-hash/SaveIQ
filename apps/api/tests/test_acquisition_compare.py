"""Ranking + caveats for the acquisition advisor."""

from __future__ import annotations

import pytest

from app.services.acquisition import BuyerProfile, compare_paths
from app.services.acquisition.models import AcquisitionKind, AcquisitionOption

CHEAP_RETAIL = AcquisitionOption(
    kind=AcquisitionKind.retail,
    label="Buy outright + BYOD",
    provider="Apple + BYOD",
    upfront_cents=100_000,
    plan_monthly_cents=5_000,
    resale_value_cents=40_000,
    resale_at_months=24,
    verify=False,
)
PRICEY_FINANCING = AcquisitionOption(
    kind=AcquisitionKind.financing,
    label="Carrier 0% + premium plan",
    provider="Rogers",
    device_monthly_cents=5_000,
    term_months=24,
    plan_monthly_cents=8_500,
    plan_credit_cents=1_500,
    plan_credit_months=24,
    resale_value_cents=40_000,
    resale_at_months=24,
    lock_in_months=24,
    verify=False,
)
LEASE_RETURN = AcquisitionOption(
    kind=AcquisitionKind.lease,
    label="Bring-It-Back",
    provider="Telus",
    device_monthly_cents=2_000,
    term_months=24,
    residual_cents=55_000,
    returns_at_term=True,
    plan_monthly_cents=8_500,
    plan_credit_cents=1_500,
    plan_credit_months=24,
    lock_in_months=24,
    verify=False,
)

P24 = BuyerProfile(horizon_months=24)


def test_ranks_by_effective_total_ascending() -> None:
    rec = compare_paths([PRICEY_FINANCING, CHEAP_RETAIL], P24)
    labels = [t.option_label for t in rec.ranked]
    assert labels[0] == "Buy outright + BYOD"
    assert rec.best_label == "Buy outright + BYOD"
    assert rec.runner_up_gap_cents == (
        rec.ranked[1].effective_total_cents - rec.ranked[0].effective_total_cents
    )
    assert rec.runner_up_gap_cents > 0


def test_empty_options_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        compare_paths([], P24)


def test_cheapest_path_owning_nothing_earns_a_caveat() -> None:
    # churner: the lease-return path is cheapest AND leaves nothing owned
    churn = BuyerProfile(horizon_months=24, upgrades_every_months=24)
    rec = compare_paths([LEASE_RETURN, PRICEY_FINANCING], churn)
    assert rec.ranked[0].option_label == "Bring-It-Back"
    assert rec.ranked[0].owns_at_horizon is False
    assert any("own nothing" in c.lower() for c in rec.caveats)


def test_long_holder_gets_the_lease_is_a_trap_caveat() -> None:
    rec = compare_paths([CHEAP_RETAIL, LEASE_RETURN], BuyerProfile(horizon_months=24))
    assert rec.best_label == "Buy outright + BYOD"
    assert any("flexibility you won't use" in c.lower() for c in rec.caveats)


def test_business_profile_flags_the_support_lever() -> None:
    rec = compare_paths(
        [CHEAP_RETAIL, PRICEY_FINANCING], BuyerProfile(horizon_months=24, is_business=True)
    )
    assert any("priority support" in c.lower() for c in rec.caveats)


def test_lock_in_on_the_recommended_path_is_called_out() -> None:
    rec = compare_paths([PRICEY_FINANCING], P24)
    assert any("locks you in" in c.lower() for c in rec.caveats)


def test_close_race_says_pick_on_non_price_factors() -> None:
    a = CHEAP_RETAIL.model_copy(update={"label": "A"})
    b = CHEAP_RETAIL.model_copy(update={"label": "B", "upfront_cents": 100_500})
    rec = compare_paths([a, b], P24)
    assert any("pick on lock-in" in c.lower() for c in rec.caveats)


def test_verify_first_is_always_populated() -> None:
    rec = compare_paths([CHEAP_RETAIL], P24)
    assert len(rec.verify_first) >= 2
    assert any("5g" in v.lower() for v in rec.verify_first)


def test_ranked_entries_all_carry_a_verify_caveat() -> None:
    rec = compare_paths(
        [CHEAP_RETAIL.model_copy(update={"verify": True, "as_of": "2026-09-09"})], P24
    )
    assert all(any("estimate" in n.lower() for n in t.assumptions) for t in rec.ranked)
