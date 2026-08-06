"""AI router package (Gate 6A mock-only)."""

from app.services.router.contract import (
    AI_ROUTER_AVAILABLE_MODELS,
    AI_ROUTER_FALLBACK_MODEL,
    IntentComplexity,
    RouterDecision,
    RouteRequest,
)
from app.services.router.mock_router import MockRouter

__all__ = [
    "AI_ROUTER_AVAILABLE_MODELS",
    "AI_ROUTER_FALLBACK_MODEL",
    "IntentComplexity",
    "MockRouter",
    "RouteRequest",
    "RouterDecision",
]
