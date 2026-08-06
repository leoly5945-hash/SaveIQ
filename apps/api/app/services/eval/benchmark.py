"""Offline router/provider benchmark framework (Gate 9)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Literal

from app.services.bandit.agent import ContextualBanditAgent
from app.services.bandit.features import FEATURE_NAMES, BanditContext, build_feature_vector
from app.services.bandit.neural import NeuralBanditAgent
from app.services.bandit.rlhf import RlhfPolicyAgent

PolicyName = Literal["random", "rule", "linucb", "neural", "rlhf"]


@dataclass(frozen=True)
class BenchmarkRow:
    policy: str
    samples: int
    cumulative_reward: float
    average_reward: float
    average_latency_ms: float
    estimated_cost_usd: float
    agreement_with_logged: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "samples": self.samples,
            "cumulative_reward": self.cumulative_reward,
            "average_reward": self.average_reward,
            "average_latency_ms": self.average_latency_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "agreement_with_logged": self.agreement_with_logged,
            # Proxy CTR: fraction of high-reward (>=0.6) accepted actions.
            "ctr_proxy": self.average_reward,
        }


def run_router_benchmark(
    logs: list[dict[str, Any]] | None = None,
    *,
    policies: tuple[PolicyName, ...] = ("random", "rule", "linucb", "neural", "rlhf"),
    seed: int = 7,
) -> dict[str, Any]:
    dataset = logs if logs else _synthetic_logs(seed=seed)
    rows = [
        _evaluate_policy(policy, dataset, seed=seed + index).as_dict()
        for index, policy in enumerate(policies)
    ]
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples": len(dataset),
        "policies": rows,
        "notes": [
            "CTR is proxied by average reward on logged replay.",
            "Neural/RLHF fall back internally until min samples are reached.",
        ],
    }


def _evaluate_policy(
    policy: PolicyName,
    logs: list[dict[str, Any]],
    *,
    seed: int,
) -> BenchmarkRow:
    rng = random.Random(seed)
    actions = ("openai", "anthropic", "mock", "deepseek", "qwen", "ernie")
    feature_dim = len(FEATURE_NAMES)
    linucb = ContextualBanditAgent(
        actions=actions,
        feature_dim=feature_dim,
        epsilon=0.05,
        min_samples_ready=5,
        rng=random.Random(seed),
    )
    neural = NeuralBanditAgent(
        actions=actions,
        feature_dim=feature_dim,
        epsilon=0.05,
        min_samples_ready=8,
        rng=random.Random(seed + 1),
    )
    rlhf = RlhfPolicyAgent(
        actions=actions,
        feature_dim=feature_dim,
        min_samples_ready=8,
        rng=random.Random(seed + 2),
    )

    cumulative = 0.0
    latency_total = 0.0
    cost_total = 0.0
    agreements = 0
    used = 0

    for row in logs:
        vector = _vector_from_row(row)
        logged_action = str(row.get("action") or "mock")
        reward = float(row.get("reward") or 0.0)
        latency = float(row.get("latency_ms") or 0.0)
        cost = float(row.get("estimated_cost_usd") or 0.0)
        rule_action = str(row.get("rule_action") or logged_action)

        if policy == "random":
            chosen = rng.choice(list(actions))
        elif policy == "rule":
            chosen = rule_action
        elif policy == "linucb":
            chosen = linucb.choose_action(vector, force_explore=False).action
        elif policy == "neural":
            neural_choice = neural.choose_action(vector, force_explore=False)
            chosen = neural_choice.action if neural_choice.ready else rule_action
        else:
            rlhf_choice = rlhf.choose_action(vector)
            chosen = rlhf_choice.action if rlhf_choice.ready else rule_action

        used += 1
        if chosen == logged_action:
            cumulative += reward
            agreements += 1
            latency_total += latency
            cost_total += cost
        # Progressive learning on logged action/reward.
        linucb.update(vector, logged_action, reward)
        neural.update(vector, logged_action, reward)
        rlhf.update(vector, logged_action, reward)

    avg_reward = cumulative / used if used else 0.0
    return BenchmarkRow(
        policy=policy,
        samples=used,
        cumulative_reward=cumulative,
        average_reward=avg_reward,
        average_latency_ms=(latency_total / agreements) if agreements else 0.0,
        estimated_cost_usd=cost_total,
        agreement_with_logged=(agreements / used) if used else 0.0,
    )


def _vector_from_row(row: dict[str, Any]) -> list[float]:
    features = row.get("features")
    if isinstance(features, list) and len(features) == len(FEATURE_NAMES):
        return [float(value) for value in features]
    if isinstance(features, dict):
        try:
            return [float(features[name]) for name in FEATURE_NAMES]
        except (KeyError, TypeError, ValueError):
            pass
    query = str(row.get("query_text") or "benchmark query")
    return build_feature_vector(BanditContext(query_text=query))


def _synthetic_logs(*, seed: int, n: int = 40) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    actions = ["openai", "anthropic", "mock", "deepseek", "qwen"]
    logs: list[dict[str, Any]] = []
    for index in range(n):
        query = f"find deal {index} {'complex organic groceries' if index % 5 == 0 else 'milk'}"
        vector = build_feature_vector(BanditContext(query_text=query))
        action = rng.choice(actions)
        reward = rng.uniform(0.2, 0.95)
        logs.append(
            {
                "features": {
                    name: value for name, value in zip(FEATURE_NAMES, vector, strict=True)
                },
                "action": action,
                "rule_action": "openai" if "milk" in query else "anthropic",
                "reward": reward,
                "latency_ms": rng.uniform(80, 900),
                "estimated_cost_usd": rng.uniform(0.0005, 0.02),
                "query_text": query,
            }
        )
    return logs
