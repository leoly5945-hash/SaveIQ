"""Mock AI router retained for Gate 6A compatibility tests and simple route().

Gate 6B production flow uses ``AiRouter`` in ``ai_router.py``.
"""

from __future__ import annotations

from app.core.settings import Settings
from app.services.canary.effective import effective_ai_router_mode, is_feature_active
from app.services.router.contract import (
    AI_ROUTER_FALLBACK_MODEL,
    IntentComplexity,
    RouterDecision,
    RouteRequest,
    classify_complexity,
)


class MockRouter:
    """Feature-flagged mock model router (selection only, no provider calls)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(self, request: RouteRequest) -> RouterDecision:
        default_model = self._settings.ai_router_default_model or AI_ROUTER_FALLBACK_MODEL
        complexity = classify_complexity(request.query_text)

        if (
            not is_feature_active("router", settings=self._settings)
            or effective_ai_router_mode(self._settings) == "disabled"
        ):
            return RouterDecision(
                selected_model=default_model,
                selected_provider="none",
                reason="AI router disabled; using default model",
                fallback_model=AI_ROUTER_FALLBACK_MODEL,
                fallback_provider="none",
                complexity=complexity,
            )

        if complexity == IntentComplexity.COMPLEX:
            reason = "mock route: long query kept on deterministic intent-parser-v0"
        elif complexity == IntentComplexity.MEDIUM:
            reason = "mock route: medium query kept on default model"
        else:
            reason = "mock route: short query kept on default model"

        return RouterDecision(
            selected_model=default_model,
            selected_provider="mock",
            reason=reason,
            fallback_model=AI_ROUTER_FALLBACK_MODEL,
            fallback_provider="none",
            complexity=complexity,
        )
