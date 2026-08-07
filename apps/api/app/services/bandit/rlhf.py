"""REINFORCE-style policy updates for router actions (Gate 9 RLHF stub)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any


def _softmax(logits: list[float]) -> list[float]:
    peak = max(logits) if logits else 0.0
    exps = [math.exp(value - peak) for value in logits]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


@dataclass(frozen=True)
class RlhfChoice:
    action: str
    probs: dict[str, float]
    explored: bool
    ready: bool
    reason: str


class RlhfPolicyAgent:
    """
    Linear softmax policy trained with REINFORCE on human/system rewards.

    This is an offline-friendly stub: safe defaults keep it behind a feature flag and
    require minimum samples before influencing routing.
    """

    def __init__(
        self,
        *,
        actions: tuple[str, ...],
        feature_dim: int,
        learning_rate: float = 0.05,
        min_samples_ready: int = 30,
        rng: random.Random | None = None,
    ) -> None:
        self.actions = tuple(actions)
        self.feature_dim = feature_dim
        self.learning_rate = learning_rate
        self.min_samples_ready = min_samples_ready
        self._rng = rng or random.Random(11)
        scale = 0.05
        self._theta: dict[str, list[float]] = {
            action: [self._rng.uniform(-scale, scale) for _ in range(feature_dim)]
            for action in self.actions
        }
        self._updates = 0
        self._cumulative_reward = 0.0
        self._counts: dict[str, int] = {action: 0 for action in self.actions}

    @property
    def ready(self) -> bool:
        return self._updates >= self.min_samples_ready

    def choose_action(
        self,
        context: list[float],
        *,
        available_actions: list[str] | None = None,
    ) -> RlhfChoice:
        x = [float(v) for v in context]
        candidates = [
            action for action in (available_actions or list(self.actions)) if action in self._theta
        ]
        if not candidates:
            raise ValueError("No RLHF actions available")
        logits = [self._dot(self._theta[action], x) for action in candidates]
        probs = _softmax(logits)
        # Sample from policy (exploration inherent).
        pick = self._rng.random()
        cumulative = 0.0
        selected = candidates[-1]
        for action, prob in zip(candidates, probs, strict=True):
            cumulative += prob
            if pick <= cumulative:
                selected = action
                break
        prob_map = {action: prob for action, prob in zip(candidates, probs, strict=True)}
        return RlhfChoice(
            action=selected,
            probs=prob_map,
            explored=True,
            ready=self.ready,
            reason="rlhf softmax sample" if self.ready else "rlhf cold-start",
        )

    def update(self, context: list[float], action: str, reward: float) -> None:
        if action not in self._theta:
            return
        x = [float(v) for v in context]
        logits = [self._dot(self._theta[candidate], x) for candidate in self.actions]
        probs = _softmax(logits)
        # REINFORCE: θ <- θ + lr * R * ∇logπ(a|x)
        for index, candidate in enumerate(self.actions):
            indicator = 1.0 if candidate == action else 0.0
            advantage = indicator - probs[index]
            for feature_index in range(self.feature_dim):
                self._theta[candidate][feature_index] += (
                    self.learning_rate * float(reward) * advantage * x[feature_index]
                )
        self._counts[action] += 1
        self._updates += 1
        self._cumulative_reward += float(reward)

    def status(self) -> dict[str, Any]:
        return {
            "algorithm": "rlhf_reinforce",
            "ready": self.ready,
            "sample_count": self._updates,
            "min_samples_ready": self.min_samples_ready,
            "actions": list(self.actions),
            "action_counts": dict(self._counts),
            "cumulative_reward": self._cumulative_reward,
        }

    def reset(self) -> None:
        scale = 0.05
        self._theta = {
            action: [self._rng.uniform(-scale, scale) for _ in range(self.feature_dim)]
            for action in self.actions
        }
        self._updates = 0
        self._cumulative_reward = 0.0
        self._counts = {action: 0 for action in self.actions}

    @staticmethod
    def _dot(weights: list[float], x: list[float]) -> float:
        return sum(weight * value for weight, value in zip(weights, x, strict=True))
