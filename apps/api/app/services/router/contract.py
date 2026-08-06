"""AI router contracts for Gate 6A (mock-only model selection)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

AI_ROUTER_FALLBACK_MODEL = "intent-parser-v0"
AI_ROUTER_AVAILABLE_MODELS: tuple[str, ...] = (AI_ROUTER_FALLBACK_MODEL,)


class IntentComplexity(StrEnum):
    """Heuristic complexity labels used by the mock router for observability.

    These labels do not unlock live models. They only describe why the mock
    router chose its deterministic selection.
    """

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class RouteRequest(BaseModel):
    """Input for a single AI router decision before intent parsing.

    The router never browses, scrapes, or calls providers. It only chooses
    among the locally available mock model identities.
    """

    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(min_length=1, max_length=240)
    user_id: str | None = Field(default=None, max_length=120)
    intent_type: str = Field(default="recommendation", min_length=1, max_length=64)

    @field_validator("query_text", "intent_type")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("user_id")
    @classmethod
    def strip_optional_user_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RouterDecision(BaseModel):
    """Deterministic routing decision returned to the intent parser.

    ``selected_model`` is the model identity to prefer. ``fallback_model`` is
    always the safe deterministic parser identity. Gate 6A never returns a live
    provider model name.
    """

    model_config = ConfigDict(extra="forbid")

    selected_model: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=240)
    fallback_model: str = Field(default=AI_ROUTER_FALLBACK_MODEL, min_length=1, max_length=120)
    complexity: IntentComplexity = IntentComplexity.SIMPLE

    @field_validator("selected_model", "reason", "fallback_model")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()
