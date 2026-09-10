"""Types for the acquisition advisor: an option, and the buyer asking."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AcquisitionKind(StrEnum):
    retail = "retail"  # pay the full price now, own it outright
    financing = "financing"  # 0% installments; you own it when the term ends
    lease = "lease"  # bring-it-back / balloon; return at term or pay a residual to own
    bundle = "bundle"  # device + a required plan, usually with monthly bill credits
    refurb = "refurb"  # certified refurbished / open-box / previous generation


class AcquisitionOption(BaseModel):
    """One concrete way to acquire a specific product, with its cash flows.

    All amounts are integer cents in the catalogue currency. A field left at 0
    simply doesn't apply to this option (e.g. ``residual_cents`` on a retail buy).
    """

    kind: AcquisitionKind
    label: str
    provider: str | None = None

    upfront_cents: int = 0  # due at signing
    device_monthly_cents: int = 0  # one installment payment
    term_months: int = 0  # installment term; 0 means paid entirely upfront
    residual_cents: int = 0  # balloon payment to own the device at term end (lease)
    returns_at_term: bool = False  # lease: the device goes back unless the residual is paid

    # Plan side — only when the option requires or bundles a specific plan.
    plan_monthly_cents: int = 0
    plan_credit_cents: int = 0  # monthly bill credit tied to taking this option
    plan_credit_months: int = 0  # how long that credit lasts

    # Value you keep if you own the device at the horizon.
    resale_value_cents: int = 0
    resale_at_months: int = 36

    lock_in_months: int = 0  # early-exit penalty window (remaining device balance owed)

    as_of: str = ""  # ISO date these numbers were checked
    verify: bool = True  # numbers are estimates until researched and confirmed
    notes: list[str] = Field(default_factory=list)


class BuyerProfile(BaseModel):
    """The person asking. Drives horizon, discounting, and which warnings fire."""

    horizon_months: int = 36
    # Opportunity cost of cash tied up now, annualised. A business that can
    # deploy capital sets this above 0 (e.g. 0.06); a consumer leaves it at 0.
    annual_discount_rate: float = 0.0
    # If the buyer genuinely replaces the device this often, lease / bundle churn
    # is a real option rather than a trap. ``None`` = keeps devices long.
    upgrades_every_months: int | None = None
    values_ownership: bool = True
    service_sensitivity: Literal["low", "normal", "high"] = "normal"
    is_business: bool = False
