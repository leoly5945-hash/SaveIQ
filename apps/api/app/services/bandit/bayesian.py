"""Lightweight Bayesian optimization for router hyperparameters (Gate 9)."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Bound:
    name: str
    low: float
    high: float


@dataclass(frozen=True)
class BayesianOptimizeResult:
    best_params: dict[str, float]
    best_score: float
    history: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "best_params": self.best_params,
            "best_score": self.best_score,
            "trials": len(self.history),
            "history": self.history[-20:],
        }


def bayesian_optimize(
    objective: Callable[[dict[str, float]], float],
    bounds: list[Bound],
    *,
    n_init: int = 5,
    n_iter: int = 15,
    rng: random.Random | None = None,
) -> BayesianOptimizeResult:
    """
    Minimal GP-UCB style optimizer (RBF kernel, pure Python).

    Designed for offline tuning of epsilon/alpha/beta/gamma on logged rewards.
    """
    if not bounds:
        raise ValueError("bounds required")
    engine = rng or random.Random(42)
    xs: list[list[float]] = []
    ys: list[float] = []
    history: list[dict[str, Any]] = []

    def sample_random() -> list[float]:
        return [engine.uniform(bound.low, bound.high) for bound in bounds]

    def to_params(vector: list[float]) -> dict[str, float]:
        return {bound.name: float(value) for bound, value in zip(bounds, vector, strict=True)}

    for _ in range(max(1, n_init)):
        vector = sample_random()
        params = to_params(vector)
        score = float(objective(params))
        xs.append(vector)
        ys.append(score)
        history.append({"params": params, "score": score, "phase": "init"})

    for _ in range(max(0, n_iter)):
        candidates = [sample_random() for _ in range(32)]
        best_candidate = candidates[0]
        best_ucb = float("-inf")
        for candidate in candidates:
            mean, std = _gp_predict(candidate, xs, ys)
            ucb = mean + 1.5 * std
            if ucb > best_ucb:
                best_ucb = ucb
                best_candidate = candidate
        params = to_params(best_candidate)
        score = float(objective(params))
        xs.append(best_candidate)
        ys.append(score)
        history.append({"params": params, "score": score, "phase": "ucb"})

    best_index = max(range(len(ys)), key=lambda index: ys[index])
    return BayesianOptimizeResult(
        best_params=to_params(xs[best_index]),
        best_score=ys[best_index],
        history=history,
    )


def _rbf(a: list[float], b: list[float], lengthscale: float = 0.35) -> float:
    dist2 = sum((x - y) ** 2 for x, y in zip(a, b, strict=True))
    return math.exp(-0.5 * dist2 / (lengthscale**2))


def _gp_predict(
    x: list[float],
    xs: list[list[float]],
    ys: list[float],
    noise: float = 1e-3,
) -> tuple[float, float]:
    if not xs:
        return 0.0, 1.0
    k = [_rbf(x, xi) for xi in xs]
    # Diagonal approximation for speed/stability on tiny problems.
    weights = []
    denom = 0.0
    for value in k:
        w = value / (value + noise)
        weights.append(w)
        denom += w
    if denom <= 1e-12:
        return 0.0, 1.0
    mean = sum(weights[i] * ys[i] for i in range(len(ys))) / denom
    # Predictive std shrinks with kernel mass.
    std = max(0.05, 1.0 - min(1.0, denom / (len(xs) + 1.0)))
    return mean, std


def tune_reward_hyperparameters(
    logs: list[dict[str, Any]],
    *,
    n_init: int = 4,
    n_iter: int = 10,
) -> BayesianOptimizeResult:
    """Offline tune epsilon/alpha/beta/gamma using logged rewards as a proxy objective."""

    def objective(params: dict[str, float]) -> float:
        if not logs:
            return 0.0
        alpha = params["alpha"]
        beta = params["beta"]
        gamma = params["gamma"]
        # Proxy: higher weight on historically strong quality logs.
        total = 0.0
        for row in logs:
            reward = float(row.get("reward") or 0.0)
            breakdown = row.get("reward_breakdown") or {}
            quality = float(breakdown.get("quality", reward))
            cost_term = float(breakdown.get("cost_term", 0.5))
            latency_term = float(breakdown.get("latency_term", 0.5))
            estimated = alpha * quality + beta * cost_term + gamma * latency_term
            # Prefer params whose reweighted estimate stays close to observed reward.
            total -= abs(estimated - reward)
            total += 0.05 * reward
        # Mild preference for moderate epsilon.
        total -= abs(params["epsilon"] - 0.1) * 0.1
        return total / max(len(logs), 1)

    bounds = [
        Bound("epsilon", 0.01, 0.4),
        Bound("alpha", 0.1, 0.8),
        Bound("beta", 0.05, 0.6),
        Bound("gamma", 0.05, 0.6),
    ]
    return bayesian_optimize(objective, bounds, n_init=n_init, n_iter=n_iter)
