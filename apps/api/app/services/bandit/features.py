"""Context feature extraction for the Gate 7/8 contextual bandit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.router.contract import IntentComplexity, classify_complexity
from app.services.user.embedding import EMBEDDING_DIM, empty_embedding

BASE_FEATURE_NAMES: tuple[str, ...] = (
    "bias",
    "query_len_norm",
    "word_count_norm",
    "complexity_simple",
    "complexity_medium",
    "complexity_complex",
    "intent_recommendation",
    "intent_search",
    "market_ca",
    "hour_sin",
    "hour_cos",
    "has_user_id",
)

PERSONALIZATION_FEATURE_NAMES: tuple[str, ...] = (
    "session_count_norm",
    "click_rate_norm",
    "avg_query_length_norm",
    "opt_out",
    *(f"emb_{index}" for index in range(EMBEDDING_DIM)),
)

FEATURE_NAMES: tuple[str, ...] = BASE_FEATURE_NAMES + PERSONALIZATION_FEATURE_NAMES


@dataclass(frozen=True)
class BanditContext:
    """Raw request context used to build a feature vector."""

    query_text: str
    intent_type: str = "recommendation"
    market: str = "CA"
    user_id: str | None = None
    hour_utc: int | None = None
    personalization: dict[str, float] = field(default_factory=dict)


def build_feature_vector(context: BanditContext) -> list[float]:
    """Return a fixed-length dense feature vector (pure Python, no numpy)."""
    query = context.query_text.strip()
    words = query.split()
    complexity = classify_complexity(query)
    hour = context.hour_utc
    if hour is None:
        hour = datetime.now(UTC).hour
    hour_angle = (hour % 24) / 24.0
    hour_sin, hour_cos = _unit_circle(hour_angle)

    intent = context.intent_type.strip().lower()
    market = context.market.strip().upper()
    personal = context.personalization or {}
    emb = [float(personal.get(f"emb_{index}", 0.0)) for index in range(EMBEDDING_DIM)]
    if all(value == 0.0 for value in emb) and not personal:
        emb = empty_embedding()

    return [
        1.0,  # bias
        min(len(query) / 240.0, 1.0),
        min(len(words) / 60.0, 1.0),
        1.0 if complexity == IntentComplexity.SIMPLE else 0.0,
        1.0 if complexity == IntentComplexity.MEDIUM else 0.0,
        1.0 if complexity == IntentComplexity.COMPLEX else 0.0,
        1.0 if intent == "recommendation" else 0.0,
        1.0 if intent == "search" else 0.0,
        1.0 if market == "CA" else 0.0,
        hour_sin,
        hour_cos,
        1.0 if context.user_id else 0.0,
        float(personal.get("session_count_norm", 0.0)),
        float(personal.get("click_rate_norm", 0.0)),
        float(personal.get("avg_query_length_norm", 0.0)),
        float(personal.get("opt_out", 0.0)),
        *emb,
    ]


def features_as_dict(vector: list[float]) -> dict[str, float]:
    return {name: float(value) for name, value in zip(FEATURE_NAMES, vector, strict=True)}


def context_metadata(context: BanditContext) -> dict[str, Any]:
    complexity = classify_complexity(context.query_text)
    return {
        "query_len": len(context.query_text.strip()),
        "word_count": len(context.query_text.split()),
        "complexity": complexity.value,
        "intent_type": context.intent_type,
        "market": context.market,
        "has_user_id": bool(context.user_id),
        "personalization_keys": sorted(context.personalization.keys()),
    }


def _unit_circle(fraction: float) -> tuple[float, float]:
    import math

    angle = 2.0 * math.pi * fraction
    return math.sin(angle), math.cos(angle)
