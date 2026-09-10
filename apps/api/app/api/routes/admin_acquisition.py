"""Admin: acquisition advisor (Layer 2) — compare ways to acquire a product.

Read-only, admin token. `GET /admin/acquisition/data` shows the loaded
category/channel rulesets; `GET /admin/acquisition/compare` composes the options
for a product (by demo slug, or by explicit retail price + category) and runs the
TCO comparison for one buyer profile. The public / LLM-narrated surface comes
later — this is the staging window into the engine.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.services.acquisition import (
    BuyerProfile,
    PathRecommendation,
    ProductContext,
    compare_paths,
    compose_options,
)
from app.services.acquisition.catalog import (
    load_demo_products,
    load_depreciation,
    load_plans,
    load_programs,
)

router = APIRouter(
    prefix="/admin/acquisition",
    tags=["admin-acquisition"],
    dependencies=[Depends(require_admin)],
)


class DataSummary(BaseModel):
    programs_as_of: str
    programs_disclaimer: str
    programs: list[dict[str, object]]
    plans: list[dict[str, object]]
    depreciation_categories: list[str]
    demo_slugs: list[str]


@router.get("/data", response_model=DataSummary)
def data_summary() -> DataSummary:
    progs = load_programs()
    plans = load_plans()
    return DataSummary(
        programs_as_of=progs.as_of,
        programs_disclaimer=progs.disclaimer,
        programs=[
            {"id": p.id, "kind": p.kind, "label": p.label, "categories": p.categories or ["*"]}
            for p in progs.programs
        ],
        plans=[
            {"id": p.id, "label": p.label, "monthly_cents": p.monthly_cents} for p in plans.plans
        ],
        depreciation_categories=sorted(load_depreciation().curves),
        demo_slugs=[p.slug for p in load_demo_products().products],
    )


@router.get("/compare", response_model=PathRecommendation)
def compare(
    slug: Annotated[str | None, Query(description="demo product slug")] = None,
    retail_price_cents: Annotated[int | None, Query(ge=1)] = None,
    category: Annotated[str | None, Query()] = None,
    brand: Annotated[str | None, Query()] = None,
    tier: Annotated[str, Query()] = "flagship",
    carrier_eligible: Annotated[bool | None, Query()] = None,
    horizon_months: Annotated[int, Query(ge=1, le=120)] = 36,
    annual_discount_rate: Annotated[float, Query(ge=0.0, le=0.5)] = 0.0,
    upgrades_every_months: Annotated[int | None, Query(ge=1, le=120)] = None,
    values_ownership: Annotated[bool, Query()] = True,
    service_sensitivity: Annotated[Literal["low", "normal", "high"], Query()] = "normal",
    is_business: Annotated[bool, Query()] = False,
) -> PathRecommendation:
    if slug:
        product = load_demo_products().get(slug)
        if product is None:
            raise HTTPException(status_code=404, detail=f"no demo product {slug!r}")
        ctx = ProductContext(
            retail_price_cents=product.retail_price_cents,
            category=product.category,
            brand=product.brand,
            tier=product.tier,
            carrier_eligible=product.carrier_eligible,
        )
    elif retail_price_cents and category:
        ctx = ProductContext(
            retail_price_cents=retail_price_cents,
            category=category,
            brand=brand,
            tier=tier,
            carrier_eligible=carrier_eligible,
        )
    else:
        raise HTTPException(status_code=422, detail="pass slug, or retail_price_cents + category")

    profile = BuyerProfile(
        horizon_months=horizon_months,
        annual_discount_rate=annual_discount_rate,
        upgrades_every_months=upgrades_every_months,
        values_ownership=values_ownership,
        service_sensitivity=service_sensitivity,
        is_business=is_business,
    )
    options = compose_options(ctx, horizon_months=horizon_months)
    if not options:
        raise HTTPException(status_code=404, detail="no acquisition options for that product")
    return compare_paths(options, profile, product_slug=slug)
