"""TCO arithmetic for the acquisition advisor."""

from __future__ import annotations

from app.services.acquisition.models import AcquisitionKind, AcquisitionOption, BuyerProfile
from app.services.acquisition.tco import compute_tco


def _retail(**over: object) -> AcquisitionOption:
    base = dict(
        kind=AcquisitionKind.retail,
        label="Buy outright",
        upfront_cents=100_000,
        plan_monthly_cents=5_000,
        resale_value_cents=40_000,
        resale_at_months=24,
        verify=False,
    )
    base.update(over)
    return AcquisitionOption(**base)  # type: ignore[arg-type]


def _financing(**over: object) -> AcquisitionOption:
    base = dict(
        kind=AcquisitionKind.financing,
        label="0% financing",
        device_monthly_cents=5_000,
        term_months=24,
        plan_monthly_cents=6_000,
        plan_credit_cents=1_000,
        plan_credit_months=24,
        resale_value_cents=40_000,
        resale_at_months=24,
        verify=False,
    )
    base.update(over)
    return AcquisitionOption(**base)  # type: ignore[arg-type]


def _lease(**over: object) -> AcquisitionOption:
    base = dict(
        kind=AcquisitionKind.lease,
        label="Bring-It-Back",
        device_monthly_cents=3_000,
        term_months=24,
        residual_cents=55_000,
        returns_at_term=True,
        plan_monthly_cents=6_000,
        plan_credit_cents=1_000,
        plan_credit_months=24,
        resale_value_cents=40_000,
        resale_at_months=24,
        verify=False,
    )
    base.update(over)
    return AcquisitionOption(**base)  # type: ignore[arg-type]


P24 = BuyerProfile(horizon_months=24)


def test_retail_no_discount_is_a_plain_sum() -> None:
    t = compute_tco(_retail(), P24)
    # 100000 upfront + 5000*24 plan - 40000 resale
    assert t.nominal_total_cents == 100_000 + 120_000 - 40_000
    assert t.effective_total_cents == t.nominal_total_cents
    assert t.monthly_equivalent_cents == t.effective_total_cents // 24
    assert t.owns_at_horizon is True


def test_financing_no_discount_sums_installments_and_net_plan() -> None:
    t = compute_tco(_financing(), P24)
    assert t.device_cost_cents == 5_000 * 24
    assert t.plan_cost_cents == (6_000 - 1_000) * 24
    assert t.resale_credit_cents == 40_000
    assert t.nominal_total_cents == 120_000 + 120_000 - 40_000


def test_discount_rate_lowers_the_effective_total() -> None:
    disc = BuyerProfile(horizon_months=24, annual_discount_rate=0.12)
    assert (
        compute_tco(_financing(), disc).effective_total_cents
        < compute_tco(_financing(), P24).effective_total_cents
    )


def test_discounting_helps_the_deferred_path_more_than_the_upfront_one() -> None:
    disc = BuyerProfile(horizon_months=24, annual_discount_rate=0.12)
    retail_drop = (
        compute_tco(_retail(), P24).effective_total_cents
        - compute_tco(_retail(), disc).effective_total_cents
    )
    fin_drop = (
        compute_tco(_financing(), P24).effective_total_cents
        - compute_tco(_financing(), disc).effective_total_cents
    )
    assert fin_drop > retail_drop


def test_lease_kept_counts_the_residual_and_credits_resale() -> None:
    t = compute_tco(_lease(), BuyerProfile(horizon_months=24))  # no upgrade cycle -> kept
    assert t.owns_at_horizon is True
    assert t.device_cost_cents == 3_000 * 24 + 55_000
    assert t.resale_credit_cents == 40_000
    assert any("residual" in n.lower() for n in t.assumptions)


def test_lease_churned_drops_residual_and_resale_and_warns() -> None:
    churn = BuyerProfile(horizon_months=24, upgrades_every_months=24)
    t = compute_tco(_lease(), churn)
    assert t.owns_at_horizon is False
    assert t.device_cost_cents == 3_000 * 24  # no residual
    assert t.resale_credit_cents == 0
    assert any("own nothing" in n.lower() for n in t.assumptions)


def test_term_past_horizon_settles_the_balance_and_notes_it() -> None:
    t = compute_tco(_financing(term_months=36), P24)
    assert t.device_cost_cents == 5_000 * 24 + 5_000 * 12
    assert any(
        "past your" in n.lower() or "remaining device balance" in n.lower() for n in t.assumptions
    )


def test_credit_expiry_before_horizon_is_flagged() -> None:
    t = compute_tco(_financing(plan_credit_months=12), P24)
    # months 1-12 at 5000, months 13-24 at 6000
    assert t.plan_cost_cents == 5_000 * 12 + 6_000 * 12
    assert any("bill credit" in n.lower() for n in t.assumptions)


def test_verify_flag_adds_an_estimate_caveat() -> None:
    t = compute_tco(_retail(verify=True, as_of="2026-09-09"), P24)
    assert any("estimate" in n.lower() and "2026-09-09" in n for n in t.assumptions)
