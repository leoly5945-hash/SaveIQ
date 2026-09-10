"""Acquisition advisor (Layer 2) — how to *get* a product, not just its price.

SaveIQ's price engine (``app/services/decision/``) answers "is this price good
versus its history". This layer answers the next question a smart shopper asks:
**which acquisition path is best for me** — buy outright, 0% financing, a
bring-it-back lease, a retailer instalment plan, or refurbished — given a total
cost of ownership over my horizon and my own constraints (cash opportunity cost,
whether I upgrade often, how much I value ownership and support).

Nothing here is stored per product. A small set of category/channel rulesets
(``data/programs.json`` + ``carrier_plans.json`` + ``depreciation.json``) is
*composed* against a product's retail price + category + brand at query time
(:func:`compose_options`), then ranked (:func:`compare_paths`). Deterministic and
transparent, exactly like the price verdict — the LLM layer narrates, it does not
do the arithmetic here.
"""

from app.services.acquisition.compare import PathRecommendation, compare_paths
from app.services.acquisition.composer import ProductContext, compose_options
from app.services.acquisition.models import (
    AcquisitionKind,
    AcquisitionOption,
    BuyerProfile,
)
from app.services.acquisition.tco import TCOBreakdown, compute_tco

__all__ = [
    "AcquisitionKind",
    "AcquisitionOption",
    "BuyerProfile",
    "PathRecommendation",
    "ProductContext",
    "TCOBreakdown",
    "compare_paths",
    "compose_options",
    "compute_tco",
]
