"""Pure-Python neural contextual bandit (2-layer MLP, Gate 9)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


@dataclass(frozen=True)
class NeuralChoice:
    action: str
    scores: dict[str, float]
    explored: bool
    ready: bool
    reason: str


class NeuralBanditAgent:
    """
    Tiny MLP reward predictor per action.

    Architecture: input -> hidden (ReLU) -> scalar score, trained with SGD on observed rewards.
    Falls back callers should use LinUCB when ``ready`` is False.
    """

    def __init__(
        self,
        *,
        actions: tuple[str, ...],
        feature_dim: int,
        hidden_dim: int = 16,
        learning_rate: float = 0.05,
        epsilon: float = 0.1,
        min_samples_ready: int = 25,
        rng: random.Random | None = None,
    ) -> None:
        self.actions = tuple(actions)
        self.feature_dim = feature_dim
        self.hidden_dim = hidden_dim
        self.learning_rate = learning_rate
        self.epsilon = max(0.0, min(float(epsilon), 1.0))
        self.min_samples_ready = max(0, int(min_samples_ready))
        self._rng = rng or random.Random(9)
        self._updates = 0
        self._cumulative_reward = 0.0
        scale = 0.1
        self._w1: dict[str, list[list[float]]] = {
            action: [
                [self._rng.uniform(-scale, scale) for _ in range(feature_dim)]
                for _ in range(hidden_dim)
            ]
            for action in self.actions
        }
        self._b1: dict[str, list[float]] = {
            action: [0.0 for _ in range(hidden_dim)] for action in self.actions
        }
        self._w2: dict[str, list[float]] = {
            action: [self._rng.uniform(-scale, scale) for _ in range(hidden_dim)]
            for action in self.actions
        }
        self._b2: dict[str, float] = {action: 0.0 for action in self.actions}
        self._counts: dict[str, int] = {action: 0 for action in self.actions}

    @property
    def ready(self) -> bool:
        return self._updates >= self.min_samples_ready

    @property
    def sample_count(self) -> int:
        return self._updates

    @property
    def cumulative_reward(self) -> float:
        return self._cumulative_reward

    def choose_action(
        self,
        context: list[float],
        *,
        available_actions: list[str] | None = None,
        force_explore: bool | None = None,
    ) -> NeuralChoice:
        x = [float(v) for v in context]
        if len(x) != self.feature_dim:
            raise ValueError(f"Expected feature_dim={self.feature_dim}, got {len(x)}")
        candidates = [
            action for action in (available_actions or list(self.actions)) if action in self._w1
        ]
        if not candidates:
            raise ValueError("No available neural bandit actions")

        explore = (
            force_explore if force_explore is not None else (self._rng.random() < self.epsilon)
        )
        if explore:
            action = self._rng.choice(candidates)
            scores = {candidate: 0.0 for candidate in candidates}
            scores[action] = 1.0
            return NeuralChoice(
                action=action,
                scores=scores,
                explored=True,
                ready=self.ready,
                reason="neural epsilon explore",
            )

        scores = {action: self._forward(action, x) for action in candidates}
        best = max(candidates, key=lambda action: scores[action])
        return NeuralChoice(
            action=best,
            scores=scores,
            explored=False,
            ready=self.ready,
            reason="neural exploit" if self.ready else "neural cold-start",
        )

    def update(self, context: list[float], action: str, reward: float) -> None:
        if action not in self._w1:
            return
        x = [float(v) for v in context]
        if len(x) != self.feature_dim:
            return
        hidden, pred = self._forward_with_hidden(action, x)
        error = float(reward) - pred
        lr = self.learning_rate
        # Output layer gradients.
        for h in range(self.hidden_dim):
            self._w2[action][h] += lr * error * hidden[h]
        self._b2[action] += lr * error
        # Hidden layer gradients (ReLU).
        for h in range(self.hidden_dim):
            if hidden[h] <= 0:
                continue
            grad = error * self._w2[action][h]
            for i in range(self.feature_dim):
                self._w1[action][h][i] += lr * grad * x[i]
            self._b1[action][h] += lr * grad
        self._counts[action] += 1
        self._updates += 1
        self._cumulative_reward += float(reward)

    def status(self) -> dict[str, Any]:
        return {
            "algorithm": "neural_bandit",
            "ready": self.ready,
            "sample_count": self._updates,
            "min_samples_ready": self.min_samples_ready,
            "actions": list(self.actions),
            "action_counts": dict(self._counts),
            "feature_dim": self.feature_dim,
            "hidden_dim": self.hidden_dim,
            "epsilon": self.epsilon,
            "cumulative_reward": self._cumulative_reward,
        }

    def reset(self) -> None:
        scale = 0.1
        self._w1 = {
            action: [
                [self._rng.uniform(-scale, scale) for _ in range(self.feature_dim)]
                for _ in range(self.hidden_dim)
            ]
            for action in self.actions
        }
        self._b1 = {action: [0.0 for _ in range(self.hidden_dim)] for action in self.actions}
        self._w2 = {
            action: [self._rng.uniform(-scale, scale) for _ in range(self.hidden_dim)]
            for action in self.actions
        }
        self._b2 = {action: 0.0 for action in self.actions}
        self._counts = {action: 0 for action in self.actions}
        self._updates = 0
        self._cumulative_reward = 0.0

    def _forward(self, action: str, x: list[float]) -> float:
        _hidden, pred = self._forward_with_hidden(action, x)
        return pred

    def _forward_with_hidden(self, action: str, x: list[float]) -> tuple[list[float], float]:
        hidden: list[float] = []
        for h in range(self.hidden_dim):
            total = self._b1[action][h]
            row = self._w1[action][h]
            for i in range(self.feature_dim):
                total += row[i] * x[i]
            hidden.append(max(0.0, total))
        score = self._b2[action]
        for h in range(self.hidden_dim):
            score += self._w2[action][h] * hidden[h]
        return hidden, _sigmoid(score)
