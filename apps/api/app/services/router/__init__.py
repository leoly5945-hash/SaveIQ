"""AI router package (Gate 6A mock selection + Gate 6B providers)."""

from app.services.router.ai_router import AiRouter, build_ai_router
from app.services.router.contract import (
    AI_ROUTER_AVAILABLE_MODELS,
    AI_ROUTER_FALLBACK_MODEL,
    AI_ROUTER_PROVIDERS,
    IntentComplexity,
    RouterDecision,
    RouteRequest,
    classify_complexity,
)
from app.services.router.mock_router import MockRouter

__all__ = [
    "AI_ROUTER_AVAILABLE_MODELS",
    "AI_ROUTER_FALLBACK_MODEL",
    "AI_ROUTER_PROVIDERS",
    "AiRouter",
    "IntentComplexity",
    "MockRouter",
    "RouteRequest",
    "RouterDecision",
    "build_ai_router",
    "classify_complexity",
]
