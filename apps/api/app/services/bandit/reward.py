"""Heuristic reward calculator for Gate 7 (math team will refine later)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardBreakdown:
    reward: float
    quality: float
    cost_term: float
    latency_term: float
    user_satisfaction: float
    alpha: float
    beta: float
    gamma: float
    delta: float


def calculate_reward(
    *,
    confidence: float | None,
    estimated_cost_usd: float | None,
    latency_ms: float | None,
    success: bool,
    user_satisfaction: float | None = None,
    alpha: float = 0.5,
    beta: float = 0.3,
    gamma: float = 0.2,
    delta: float = 0.0,
    max_cost_usd: float = 0.05,
    max_latency_ms: float = 5000.0,
) -> RewardBreakdown:
    """
    reward = αq + β(1-c) + γ(1-ℓ) + δ·user_satisfaction

    user_satisfaction is optional (clicks/helpful feedback). Delta defaults to 0 so
    Gate 7 behavior is unchanged until personalization feedback is wired.
    """
    if not success:
        return RewardBreakdown(
            reward=0.0,
            quality=0.0,
            cost_term=0.0,
            latency_term=0.0,
            user_satisfaction=0.0,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            delta=delta,
        )

    quality = 0.5
    if confidence is not None:
        quality = max(0.0, min(float(confidence), 1.0))

    cost = max(0.0, float(estimated_cost_usd or 0.0))
    cost_norm = min(cost / max_cost_usd, 1.0) if max_cost_usd > 0 else 0.0
    cost_term = 1.0 - cost_norm

    latency = max(0.0, float(latency_ms or 0.0))
    latency_norm = min(latency / max_latency_ms, 1.0) if max_latency_ms > 0 else 0.0
    latency_term = 1.0 - latency_norm

    satisfaction = 0.0
    if user_satisfaction is not None:
        satisfaction = max(0.0, min(float(user_satisfaction), 1.0))

    reward = alpha * quality + beta * cost_term + gamma * latency_term + delta * satisfaction
    return RewardBreakdown(
        reward=max(0.0, min(reward, 1.0)),
        quality=quality,
        cost_term=cost_term,
        latency_term=latency_term,
        user_satisfaction=satisfaction,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        delta=delta,
    )
