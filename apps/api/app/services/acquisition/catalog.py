"""Load the hand-maintained acquisition catalogue.

``acquisition_catalog.json`` sits next to this module so a non-engineer can add a
product or fix a plan number without touching Python. Everything in it is an
**estimate** until researched — each option keeps its own ``as_of`` and
``verify`` flag, and the file carries a top-level disclaimer.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.services.acquisition.models import AcquisitionOption

CATALOG_PATH = Path(__file__).with_name("acquisition_catalog.json")


class CatalogProduct(BaseModel):
    slug: str
    title: str
    category: str
    retail_price_cents: int | None = None
    options: list[AcquisitionOption] = Field(default_factory=list)


class AcquisitionCatalog(BaseModel):
    as_of: str
    currency: str = "CAD"
    market: str = "CA"
    disclaimer: str = ""
    products: list[CatalogProduct] = Field(default_factory=list)

    def get(self, slug: str) -> CatalogProduct | None:
        key = slug.strip().lower()
        return next((p for p in self.products if p.slug.lower() == key), None)


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        raise ValueError(f"{path} must be a JSON object with a 'products' array")
    return data


@lru_cache(maxsize=1)
def load_catalog() -> AcquisitionCatalog:
    return AcquisitionCatalog.model_validate(_read(CATALOG_PATH))


def reset_catalog_cache_for_tests() -> None:
    load_catalog.cache_clear()
