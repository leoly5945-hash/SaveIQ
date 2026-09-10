"""Load the hand-maintained acquisition data.

Nothing here is per-product. The data is category- and channel-level and small
enough for one person to keep current:

* ``data/programs.json`` — ~7 acquisition-program rulesets (retail, carrier
  financing, bring-it-back, retailer 0% financing, refurb channels)
* ``data/carrier_plans.json`` — a handful of Canadian plan price points
* ``data/depreciation.json`` — resale-value curves by category and age
* ``data/demo_products.json`` — a few reference products so the composer can be
  exercised by slug; the real integration passes price + category instead

Everything is an **estimate** until researched — each file carries a disclaimer
and every composed option is tagged ``verify: true``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_DATA = Path(__file__).with_name("data")


class AcquisitionProgram(BaseModel):
    id: str
    kind: str
    label: str
    categories: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    carrier: bool = False
    term_months: int = 0
    apr: float = 0.0
    requires_plan: str | None = None
    plan_device_credit_cents: int = 0
    plan_credit_months: int = 0
    lock_in_months: int = 0
    admin_fee_cents: int = 0
    residual_pct: float = 0.0
    residual_min_cents: int = 0
    residual_max_cents: int = 0
    discount_pct: float = 0.0
    min_retail_cents: int = 0
    notes: list[str] = Field(default_factory=list)

    def applies_to(self, *, category: str, brand: str | None, retail_cents: int) -> bool:
        cats = self.categories or ["*"]
        if "*" not in cats and category not in cats:
            return False
        if self.brands and (brand or "").lower() not in self.brands:
            return False
        if self.min_retail_cents and retail_cents < self.min_retail_cents:
            return False
        return True


class CarrierPlan(BaseModel):
    id: str
    label: str
    monthly_cents: int
    full_speed_gb: int | None = None
    throttle: str | None = None
    network: str | None = None
    notes: list[str] = Field(default_factory=list)


class DemoProduct(BaseModel):
    slug: str
    title: str
    brand: str | None = None
    category: str
    tier: str = "flagship"
    retail_price_cents: int
    carrier_eligible: bool | None = None


class ProgramSet(BaseModel):
    as_of: str
    disclaimer: str = ""
    programs: list[AcquisitionProgram] = Field(default_factory=list)


class PlanSet(BaseModel):
    as_of: str
    disclaimer: str = ""
    plans: list[CarrierPlan] = Field(default_factory=list)

    def get(self, plan_id: str | None) -> CarrierPlan | None:
        if not plan_id:
            return None
        return next((p for p in self.plans if p.id == plan_id), None)


class DepreciationTable(BaseModel):
    as_of: str
    disclaimer: str = ""
    curves: dict[str, dict[str, float]] = Field(default_factory=dict)

    def resale_fraction(self, category: str, at_months: int, *, tier: str | None = None) -> float:
        curve = (
            (self.curves.get(f"{category}_{tier}") if tier else None)
            or self.curves.get(category)
            or self.curves.get("default")
            or {}
        )
        if not curve:
            return 0.0
        ages = sorted(int(k) for k in curve)
        pick = next((a for a in reversed(ages) if a <= at_months), ages[0])
        return curve[str(pick)]


class DemoProductSet(BaseModel):
    as_of: str
    disclaimer: str = ""
    products: list[DemoProduct] = Field(default_factory=list)

    def get(self, slug: str) -> DemoProduct | None:
        key = slug.strip().lower()
        return next((p for p in self.products if p.slug.lower() == key), None)


def _read(name: str) -> dict[str, Any]:
    data = json.loads((_DATA / name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a JSON object")
    return data


@lru_cache(maxsize=1)
def load_programs() -> ProgramSet:
    return ProgramSet.model_validate(_read("programs.json"))


@lru_cache(maxsize=1)
def load_plans() -> PlanSet:
    return PlanSet.model_validate(_read("carrier_plans.json"))


@lru_cache(maxsize=1)
def load_depreciation() -> DepreciationTable:
    return DepreciationTable.model_validate(_read("depreciation.json"))


@lru_cache(maxsize=1)
def load_demo_products() -> DemoProductSet:
    return DemoProductSet.model_validate(_read("demo_products.json"))


def reset_caches_for_tests() -> None:
    for fn in (load_programs, load_plans, load_depreciation, load_demo_products):
        fn.cache_clear()
