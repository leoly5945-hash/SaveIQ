"""Admin: acquisition advisor (Layer 2) — compare ways to acquire a product.

Read-only, admin token. `GET /admin/acquisition/catalog` lists the seeded
products; `GET /admin/acquisition/compare` runs the TCO comparison for one, with
the buyer profile passed as query params. The public / LLM-narrated surface comes
later — this is the staging window into the engine.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.services.acquisition import BuyerProfile, PathRecommendation, compare_paths
from app.services.acquisition.catalog import load_catalog

router = APIRouter(
    prefix="/admin/acquisition",
    tags=["admin-acquisition"],
    dependencies=[Depends(require_admin)],
)


class CatalogEntry(BaseModel):
    slug: str
    title: str
    category: str
    option_count: int


class CatalogResponse(BaseModel):
    as_of: str
    currency: str
    market: str
    disclaimer: str
    products: list[CatalogEntry]


@router.get("/catalog", response_model=CatalogResponse)
def catalog() -> CatalogResponse:
    cat = load_catalog()
    return CatalogResponse(
        as_of=cat.as_of,
        currency=cat.currency,
        market=cat.market,
        disclaimer=cat.disclaimer,
        products=[
            CatalogEntry(
                slug=p.slug, title=p.title, category=p.category, option_count=len(p.options)
            )
            for p in cat.products
        ],
    )


@router.get("/compare", response_model=PathRecommendation)
def compare(
    slug: Annotated[str, Query(description="catalogue product slug")],
    horizon_months: Annotated[int, Query(ge=1, le=120)] = 36,
    annual_discount_rate: Annotated[float, Query(ge=0.0, le=0.5)] = 0.0,
    upgrades_every_months: Annotated[int | None, Query(ge=1, le=120)] = None,
    values_ownership: Annotated[bool, Query()] = True,
    service_sensitivity: Annotated[Literal["low", "normal", "high"], Query()] = "normal",
    is_business: Annotated[bool, Query()] = False,
) -> PathRecommendation:
    product = load_catalog().get(slug)
    if product is None or not product.options:
        raise HTTPException(status_code=404, detail=f"no acquisition options for {slug!r}")

    profile = BuyerProfile(
        horizon_months=horizon_months,
        annual_discount_rate=annual_discount_rate,
        upgrades_every_months=upgrades_every_months,
        values_ownership=values_ownership,
        service_sensitivity=service_sensitivity,
        is_business=is_business,
    )
    return compare_paths(product.options, profile, product_slug=slug)
