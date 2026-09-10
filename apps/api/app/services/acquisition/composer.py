"""Compose acquisition options for a product from the category/channel rulesets.

The engine does not store options per product. Given only what the price layer
already knows — retail price, category, brand — this turns the small
``programs.json`` / ``carrier_plans.json`` / ``depreciation.json`` data into a
concrete list of :class:`AcquisitionOption` cash-flow rows to feed
:func:`app.services.acquisition.compare.compare_paths`.

A product that matches no special program still gets "buy outright + resale" —
the advisor always has something to say.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from app.services.acquisition.catalog import (
    AcquisitionProgram,
    CarrierPlan,
    load_depreciation,
    load_plans,
    load_programs,
)
from app.services.acquisition.models import AcquisitionKind, AcquisitionOption

# Categories a phone carrier will actually put on a device agreement.
_CARRIER_CATEGORIES = frozenset({"smartphone", "cellular_tablet", "cellular_watch"})


class ProductContext(BaseModel):
    retail_price_cents: int
    category: str
    brand: str | None = None
    tier: str = "flagship"  # picks the depreciation curve, e.g. smartphone_flagship
    # None -> inferred from the category. Set False for an item no carrier stocks.
    carrier_eligible: bool | None = None


def _resale_cents(base_cents: int, ctx: ProductContext, at_months: int) -> int:
    frac = load_depreciation().resale_fraction(ctx.category, at_months, tier=ctx.tier)
    return round(base_cents * frac)


def _plan_fields(plan: CarrierPlan | None, program: AcquisitionProgram) -> dict[str, int]:
    if plan is None:
        return {}
    return {
        "plan_monthly_cents": plan.monthly_cents,
        "plan_credit_cents": program.plan_device_credit_cents,
        "plan_credit_months": program.plan_credit_months,
    }


_PLAN_SUFFIXES = (" + BYOD unlimited plan", " + BYOD plan", " + premium plan", " + BYOD")


def _label(program: AcquisitionProgram, plan: CarrierPlan | None) -> str:
    """Drop a trailing "+ … plan" from a program label when no plan attached
    (a TV / laptop / headphone doesn't carry a cell plan)."""

    if plan is not None:
        return program.label
    for suffix in _PLAN_SUFFIXES:
        if program.label.endswith(suffix):
            return program.label[: -len(suffix)]
    return program.label


def _build(
    program: AcquisitionProgram,
    ctx: ProductContext,
    *,
    horizon_months: int,
    plan: CarrierPlan | None,
) -> AcquisitionOption:
    retail = ctx.retail_price_cents
    common = dict(
        kind=AcquisitionKind(program.kind),
        label=_label(program, plan),
        provider=plan.label if plan else None,
        as_of=load_programs().as_of,
        verify=True,
        notes=list(program.notes),
        lock_in_months=program.lock_in_months,
        **_plan_fields(plan, program),
    )

    if program.kind == "retail":
        return AcquisitionOption(
            **common,
            upfront_cents=retail,
            resale_value_cents=_resale_cents(retail, ctx, horizon_months),
            resale_at_months=horizon_months,
        )

    if program.kind == "refurb":
        eff = round(retail * (1.0 - program.discount_pct))
        return AcquisitionOption(
            **common,
            upfront_cents=eff,
            resale_value_cents=_resale_cents(eff, ctx, horizon_months),
            resale_at_months=horizon_months,
        )

    if program.kind == "financing":
        term = program.term_months or 24
        monthly = math.ceil(retail / term)
        return AcquisitionOption(
            **common,
            upfront_cents=program.admin_fee_cents,
            device_monthly_cents=monthly,
            term_months=term,
            resale_value_cents=_resale_cents(retail, ctx, horizon_months),
            resale_at_months=horizon_months,
        )

    if program.kind == "lease":
        term = program.term_months or 24
        residual = round(retail * program.residual_pct)
        if program.residual_min_cents:
            residual = max(residual, program.residual_min_cents)
        if program.residual_max_cents:
            residual = min(residual, program.residual_max_cents)
        monthly = math.ceil(max(retail - residual, 0) / term)
        return AcquisitionOption(
            **common,
            device_monthly_cents=monthly,
            term_months=term,
            residual_cents=residual,
            returns_at_term=True,
            resale_value_cents=_resale_cents(retail, ctx, horizon_months),
            resale_at_months=horizon_months,
        )

    raise ValueError(f"unknown program kind {program.kind!r}")


def compose_options(ctx: ProductContext, *, horizon_months: int = 36) -> list[AcquisitionOption]:
    if ctx.retail_price_cents <= 0:
        raise ValueError("retail_price_cents must be positive")

    carrier_ok = (
        ctx.category in _CARRIER_CATEGORIES
        if ctx.carrier_eligible is None
        else ctx.carrier_eligible
    )
    plans = load_plans()
    options: list[AcquisitionOption] = []
    for program in load_programs().programs:
        if not program.applies_to(
            category=ctx.category, brand=ctx.brand, retail_cents=ctx.retail_price_cents
        ):
            continue
        if program.carrier and not carrier_ok:
            continue
        # A plan cost only attaches to carrier-eligible devices (a phone needs
        # service however you got the handset); a TV / laptop / headphone carries
        # no plan line even if the program names a default one.
        needs_plan = program.carrier or carrier_ok
        plan = plans.get(program.requires_plan) if (needs_plan and program.requires_plan) else None
        if program.carrier and plan is None:
            continue  # misconfigured carrier program
        options.append(_build(program, ctx, horizon_months=horizon_months, plan=plan))
    return options
