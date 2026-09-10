"""Total cost of ownership for one acquisition option over a buyer's horizon.

Pure arithmetic. Every cash flow is placed on a month index and, when the buyer
gives an ``annual_discount_rate``, discounted to present value so "keep the cash,
pay monthly" is scored fairly against "pay it all now". Resale value the buyer
still holds at the horizon is credited back.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.acquisition.models import AcquisitionKind, AcquisitionOption, BuyerProfile

# A lease flagged "returns at term" is treated as kept (residual paid) unless the
# buyer upgrades within this many months of the term — then it's a return.
_CHURN_SLACK_MONTHS = 3


class TCOBreakdown(BaseModel):
    option_label: str
    kind: AcquisitionKind
    horizon_months: int

    upfront_cents: int
    device_cost_cents: int  # installments in-horizon + any remaining balance + residual if kept
    plan_cost_cents: int  # (plan - credit) summed over the horizon
    resale_credit_cents: int  # value of the device you still hold at the horizon

    nominal_total_cents: int  # upfront + device + plan - resale, no discounting
    effective_total_cents: int  # same flows discounted to present value
    monthly_equivalent_cents: int  # effective_total / horizon_months

    owns_at_horizon: bool
    assumptions: list[str] = Field(default_factory=list)


def _pv(amount_cents: int, month: int, monthly_rate: float) -> float:
    if monthly_rate <= 0 or month <= 0:
        return float(amount_cents)
    return amount_cents / ((1.0 + monthly_rate) ** month)


def compute_tco(option: AcquisitionOption, profile: BuyerProfile) -> TCOBreakdown:
    horizon = max(1, profile.horizon_months)
    m_rate = max(0.0, profile.annual_discount_rate) / 12.0
    notes: list[str] = []

    nominal = 0.0
    effective = 0.0

    # 1. upfront (retail: the whole price; financing/lease: down payment or 0)
    nominal += option.upfront_cents
    effective += _pv(option.upfront_cents, 0, m_rate)

    # 2. device installments
    device_nominal = 0
    if option.term_months > 0 and option.device_monthly_cents > 0:
        paid_months = min(option.term_months, horizon)
        for k in range(1, paid_months + 1):
            device_nominal += option.device_monthly_cents
            effective += _pv(option.device_monthly_cents, k, m_rate)
        if option.term_months > horizon:
            remaining = option.device_monthly_cents * (option.term_months - horizon)
            device_nominal += remaining
            effective += _pv(remaining, horizon, m_rate)
            notes.append(
                f"Term runs {option.term_months} mo, past your {horizon}-mo horizon — "
                f"the remaining device balance is counted as settled at month {horizon}."
            )

    # 3. lease residual / balloon
    keeps_device = True
    if option.returns_at_term:
        churns = (
            profile.upgrades_every_months is not None
            and profile.upgrades_every_months <= option.term_months + _CHURN_SLACK_MONTHS
        )
        keeps_device = not churns
        if churns:
            notes.append(
                "Modelled as a return at term: you pay every installment, hand the "
                "device back, and own nothing — only sound if you replace it this often."
            )
        else:
            notes.append(
                f"Modelled as paying the {option.residual_cents / 100:.0f} residual at "
                "term to keep the device."
            )
    if keeps_device and option.residual_cents > 0 and option.term_months <= horizon:
        device_nominal += option.residual_cents
        effective += _pv(option.residual_cents, option.term_months, m_rate)

    # 4. plan cost, net of any credit tied to this option
    plan_nominal = 0
    if option.plan_monthly_cents > 0:
        credit = min(option.plan_credit_cents, option.plan_monthly_cents)
        credit_until = min(option.plan_credit_months, horizon)
        for k in range(1, horizon + 1):
            monthly = option.plan_monthly_cents - (credit if k <= credit_until else 0)
            plan_nominal += monthly
            effective += _pv(monthly, k, m_rate)
        if 0 < credit_until < horizon:
            notes.append(
                f"Bill credit of {credit / 100:.0f}/mo ends at month {credit_until}; "
                f"the plan reverts to {option.plan_monthly_cents / 100:.0f}/mo after."
            )

    # 5. resale value still held at the horizon
    resale_nominal = 0
    owns_at_horizon = option.kind != AcquisitionKind.lease or keeps_device
    if owns_at_horizon and option.resale_value_cents > 0:
        at = min(option.resale_at_months, horizon)
        resale_nominal = option.resale_value_cents
        effective -= _pv(option.resale_value_cents, at, m_rate)
        if option.resale_at_months > horizon:
            notes.append(
                f"You still own the device at month {horizon}; ~{resale_nominal / 100:.0f} "
                "residual value is credited as if sold then."
            )

    nominal += device_nominal + plan_nominal - resale_nominal
    if option.lock_in_months > 0:
        notes.append(
            f"Locked for {option.lock_in_months} mo — leaving early means paying the "
            "outstanding device balance in a lump."
        )
    if option.verify:
        notes.append(
            f"Figures are estimates as of {option.as_of or 'an unrecorded date'} — verify."
        )

    return TCOBreakdown(
        option_label=option.label,
        kind=option.kind,
        horizon_months=horizon,
        upfront_cents=option.upfront_cents,
        device_cost_cents=device_nominal,
        plan_cost_cents=plan_nominal,
        resale_credit_cents=resale_nominal,
        nominal_total_cents=round(nominal),
        effective_total_cents=round(effective),
        monthly_equivalent_cents=round(effective / horizon),
        owns_at_horizon=owns_at_horizon,
        assumptions=notes,
    )
