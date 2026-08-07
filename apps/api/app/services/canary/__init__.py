"""Gate 10C canary rollout helpers."""

from app.services.canary.context import (
    bind_canary_request,
    clear_canary_request,
    get_canary_cohort_label,
    get_canary_identity,
)

__all__ = [
    "bind_canary_request",
    "clear_canary_request",
    "get_canary_cohort_label",
    "get_canary_identity",
]
