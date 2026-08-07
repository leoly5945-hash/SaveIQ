"""AI router contracts for Gate 6A/6B."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

AI_ROUTER_FALLBACK_MODEL = "intent-parser-v0"
AI_ROUTER_AVAILABLE_MODELS: tuple[str, ...] = (
    AI_ROUTER_FALLBACK_MODEL,
    "gpt-4.1-mini",
    "claude-3-5-haiku-latest",
    "deepseek-chat",
    "qwen-plus",
    "ernie-speed-128k",
    "mock-intent-model",
)
AI_ROUTER_PROVIDERS: tuple[str, ...] = (
    "mock",
    "openai",
    "anthropic",
    "deepseek",
    "qwen",
    "ernie",
)


class IntentComplexity(StrEnum):
    """Heuristic complexity labels used by the router for provider selection."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class RouteRequest(BaseModel):
    """Input for a single AI router decision before intent parsing."""

    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(min_length=1, max_length=240)
    user_id: str | None = Field(default=None, max_length=120)
    intent_type: str = Field(default="recommendation", min_length=1, max_length=64)
    market: str = Field(default="CA", min_length=2, max_length=8)

    @field_validator("query_text", "intent_type", "market")
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
    """Routing decision returned to the intent parser / admin observability."""

    model_config = ConfigDict(extra="forbid")

    selected_model: str = Field(min_length=1, max_length=120)
    selected_provider: str = Field(default="mock", min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=240)
    fallback_model: str = Field(default=AI_ROUTER_FALLBACK_MODEL, min_length=1, max_length=120)
    fallback_provider: str = Field(default="none", min_length=1, max_length=64)
    complexity: IntentComplexity = IntentComplexity.SIMPLE
    cache_hit: bool = False
    latency_ms: float | None = None
    estimated_cost_usd: float | None = None

    @field_validator(
        "selected_model",
        "selected_provider",
        "reason",
        "fallback_model",
        "fallback_provider",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


def classify_complexity(query_text: str) -> IntentComplexity:
    word_count = len(query_text.split())
    if word_count > 50:
        return IntentComplexity.COMPLEX
    if word_count > 10:
        return IntentComplexity.MEDIUM
    return IntentComplexity.SIMPLE
