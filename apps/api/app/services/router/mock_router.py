"""Mock AI router for Gate 6A.

This router never calls an external LLM, never reads API keys, and never
selects a live provider model. Its only job is to exercise routing control
points before the existing intent parser runs.
"""

from __future__ import annotations

from app.core.settings import Settings
from app.services.router.contract import (
    AI_ROUTER_FALLBACK_MODEL,
    IntentComplexity,
    RouterDecision,
    RouteRequest,
)


class MockRouter:
    """Feature-flagged mock model router.

    Behavior:
    - feature off or mode ``disabled`` → always return ``AI_ROUTER_DEFAULT_MODEL``
    - mode ``mock`` → classify query length and return the only available model
      (``intent-parser-v0``) with an observable reason/complexity
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(self, request: RouteRequest) -> RouterDecision:
        default_model = self._settings.ai_router_default_model or AI_ROUTER_FALLBACK_MODEL

        if not self._settings.feature_ai_router or self._settings.ai_router_mode == "disabled":
            return RouterDecision(
                selected_model=default_model,
                reason="AI router disabled; using default model",
                fallback_model=AI_ROUTER_FALLBACK_MODEL,
                complexity=IntentComplexity.SIMPLE,
            )

        word_count = len(request.query_text.split())
        if word_count > 50:
            complexity = IntentComplexity.COMPLEX
            reason = "mock route: long query kept on deterministic intent-parser-v0"
        elif word_count > 10:
            complexity = IntentComplexity.MEDIUM
            reason = "mock route: medium query kept on default model"
        else:
            complexity = IntentComplexity.SIMPLE
            reason = "mock route: short query kept on default model"

        # Gate 6A only exposes the deterministic parser identity. Longer queries
        # still select intent-parser-v0; the complexity/reason fields demonstrate
        # routing observability without enabling live models.
        return RouterDecision(
            selected_model=default_model,
            reason=reason,
            fallback_model=AI_ROUTER_FALLBACK_MODEL,
            complexity=complexity,
        )
