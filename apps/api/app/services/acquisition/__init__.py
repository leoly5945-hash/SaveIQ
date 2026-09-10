"""Acquisition advisor (Layer 2) — how to *get* a product, not just its price.

SaveIQ's price engine (``app/services/decision/``) answers "is this price good
versus its history". This layer answers the next question a smart shopper asks:
**which acquisition path is best for me** — buy outright, 0% financing, a
bring-it-back lease, a device+plan bundle, or last-gen/refurb — given a total
cost of ownership over my horizon and my own constraints (cash opportunity cost,
whether I upgrade often, how much I value ownership and support).

Deterministic and transparent, exactly like the price verdict: every number is
shown, every profile-driven warning is spelled out, and there is nowhere to
express a merchant payout. The LLM layer (Layer 3) picks which options apply to a
query and narrates the result — it does not do the arithmetic here.
"""

from app.services.acquisition.compare import PathRecommendation, compare_paths
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
    "TCOBreakdown",
    "compare_paths",
    "compute_tco",
]
