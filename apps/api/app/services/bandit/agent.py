"""LinUCB contextual bandit agent (pure Python, dependency-light)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any


def _zeros(n: int) -> list[float]:
    return [0.0] * n


def _identity(n: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _matvec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(row[j] * vector[j] for j in range(len(vector))) for row in matrix]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _outer_add(matrix: list[list[float]], vector: list[float]) -> None:
    n = len(vector)
    for i in range(n):
        for j in range(n):
            matrix[i][j] += vector[i] * vector[j]


def _solve_symmetric(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve A x = b with Gaussian elimination (A is d×d, small)."""
    n = len(vector)
    aug = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return _zeros(n)
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        diag = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= diag
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            for j in range(col, n + 1):
                aug[row][j] -= factor * aug[col][j]
    return [aug[i][n] for i in range(n)]


@dataclass(frozen=True)
class BanditChoice:
    action: str
    scores: dict[str, float]
    explored: bool
    ready: bool
    reason: str


class ContextualBanditAgent:
    """Disjoint-model LinUCB with optional epsilon-greedy exploration."""

    def __init__(
        self,
        *,
        actions: tuple[str, ...] = ("openai", "anthropic", "mock"),
        feature_dim: int,
        alpha: float = 0.5,
        epsilon: float = 0.1,
        min_samples_ready: int = 10,
        rng: random.Random | None = None,
    ) -> None:
        if feature_dim < 1:
            raise ValueError("feature_dim must be >= 1")
        self.actions = tuple(actions)
        self.feature_dim = feature_dim
        self.alpha = float(alpha)
        self.epsilon = max(0.0, min(float(epsilon), 1.0))
        self.min_samples_ready = max(0, int(min_samples_ready))
        self._rng = rng or random.Random()
        self._A: dict[str, list[list[float]]] = {
            action: _identity(feature_dim) for action in self.actions
        }
        self._b: dict[str, list[float]] = {action: _zeros(feature_dim) for action in self.actions}
        self._counts: dict[str, int] = {action: 0 for action in self.actions}
        self._cumulative_reward = 0.0
        self._updates = 0

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
    ) -> BanditChoice:
        x = self._validate_context(context)
        candidates = [
            action for action in (available_actions or list(self.actions)) if action in self._A
        ]
        if not candidates:
            raise ValueError("No available bandit actions")

        explore = (
            force_explore if force_explore is not None else (self._rng.random() < self.epsilon)
        )
        if explore:
            action = self._rng.choice(candidates)
            explore_scores = {candidate: 0.0 for candidate in candidates}
            explore_scores[action] = 1.0
            return BanditChoice(
                action=action,
                scores=explore_scores,
                explored=True,
                ready=self.ready,
                reason="epsilon-greedy explore",
            )

        scores: dict[str, float] = {}
        best_action = candidates[0]
        best_score = float("-inf")
        for action in candidates:
            a_inv_x = _solve_symmetric(self._A[action], x)
            theta = _solve_symmetric(self._A[action], self._b[action])
            mean = _dot(theta, x)
            bonus = self.alpha * math.sqrt(max(_dot(x, a_inv_x), 0.0))
            score = mean + bonus
            scores[action] = score
            if score > best_score:
                best_score = score
                best_action = action
        return BanditChoice(
            action=best_action,
            scores=scores,
            explored=False,
            ready=self.ready,
            reason="linucb exploit" if self.ready else "linucb cold-start",
        )

    def update(self, context: list[float], action: str, reward: float) -> None:
        if action not in self._A:
            return
        x = self._validate_context(context)
        _outer_add(self._A[action], x)
        for i, value in enumerate(x):
            self._b[action][i] += float(reward) * value
        self._counts[action] += 1
        self._updates += 1
        self._cumulative_reward += float(reward)

    def train_offline(self, logs: list[dict[str, Any]]) -> int:
        """Train from historical dict logs with keys features/action/reward."""
        trained = 0
        for row in logs:
            features = row.get("features")
            action = row.get("action")
            reward = row.get("reward")
            if not isinstance(features, dict) and not isinstance(features, list):
                continue
            if not isinstance(action, str) or reward is None:
                continue
            vector = self._features_to_vector(features)
            self.update(vector, action, float(reward))
            trained += 1
        return trained

    def reset(self) -> None:
        self._A = {action: _identity(self.feature_dim) for action in self.actions}
        self._b = {action: _zeros(self.feature_dim) for action in self.actions}
        self._counts = {action: 0 for action in self.actions}
        self._cumulative_reward = 0.0
        self._updates = 0

    def status(self) -> dict[str, Any]:
        return {
            "algorithm": "linucb",
            "ready": self.ready,
            "sample_count": self._updates,
            "min_samples_ready": self.min_samples_ready,
            "actions": list(self.actions),
            "action_counts": dict(self._counts),
            "feature_dim": self.feature_dim,
            "alpha": self.alpha,
            "epsilon": self.epsilon,
            "cumulative_reward": self._cumulative_reward,
        }

    def export_state(self) -> dict[str, Any]:
        return {
            "actions": list(self.actions),
            "feature_dim": self.feature_dim,
            "alpha": self.alpha,
            "epsilon": self.epsilon,
            "min_samples_ready": self.min_samples_ready,
            "A": self._A,
            "b": self._b,
            "counts": self._counts,
            "cumulative_reward": self._cumulative_reward,
            "updates": self._updates,
        }

    def load_state(self, payload: dict[str, Any]) -> None:
        self.actions = tuple(str(item) for item in payload.get("actions", self.actions))
        self.feature_dim = int(payload.get("feature_dim", self.feature_dim))
        self.alpha = float(payload.get("alpha", self.alpha))
        self.epsilon = float(payload.get("epsilon", self.epsilon))
        self.min_samples_ready = int(payload.get("min_samples_ready", self.min_samples_ready))
        self._A = {
            str(action): [[float(v) for v in row] for row in matrix]
            for action, matrix in dict(payload.get("A", {})).items()
        }
        self._b = {
            str(action): [float(v) for v in vector]
            for action, vector in dict(payload.get("b", {})).items()
        }
        self._counts = {
            str(action): int(count) for action, count in dict(payload.get("counts", {})).items()
        }
        self._cumulative_reward = float(payload.get("cumulative_reward", 0.0))
        self._updates = int(payload.get("updates", 0))

    def _validate_context(self, context: list[float]) -> list[float]:
        if len(context) != self.feature_dim:
            raise ValueError(f"Expected feature_dim={self.feature_dim}, got {len(context)}")
        return [float(value) for value in context]

    def _features_to_vector(self, features: list[float] | dict[str, float]) -> list[float]:
        if isinstance(features, list):
            return self._validate_context([float(v) for v in features])
        from app.services.bandit.features import FEATURE_NAMES

        try:
            return self._validate_context([float(features[name]) for name in FEATURE_NAMES])
        except (KeyError, TypeError, ValueError):
            values = [float(v) for v in features.values()]
            padded = values[: self.feature_dim] + [0.0] * max(0, self.feature_dim - len(values))
            return padded
