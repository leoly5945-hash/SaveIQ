"""Static token cost estimates for Gate 6B (log-only, no budget hard-stop)."""

from __future__ import annotations

from dataclasses import dataclass

# USD per 1M tokens. Approximate public list prices for logging only.
_MODEL_RATES_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "deepseek-chat": (0.14, 0.28),
    "qwen-plus": (0.40, 1.20),
    "ernie-speed-128k": (0.20, 0.60),
    "mock-intent-model": (0.0, 0.0),
}
_DEFAULT_RATE = (1.0, 3.0)


@dataclass(frozen=True)
class CostEstimate:
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    model: str
    provider: str


def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> CostEstimate:
    prompt_rate, completion_rate = _MODEL_RATES_USD_PER_1M.get(model, _DEFAULT_RATE)
    cost = (prompt_tokens / 1_000_000.0) * prompt_rate + (
        completion_tokens / 1_000_000.0
    ) * completion_rate
    return CostEstimate(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=round(cost, 8),
        model=model,
        provider=provider,
    )
