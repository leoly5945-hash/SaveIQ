"""Offline evaluation helpers for Gate 7 bandit vs rule-based baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.bandit.agent import ContextualBanditAgent
from app.services.bandit.features import FEATURE_NAMES


@dataclass(frozen=True)
class OfflineEvaluationResult:
    samples: int
    bandit_cumulative_reward: float
    rule_cumulative_reward: float
    regret_vs_logged: float
    agreement_rate: float
    action_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "bandit_cumulative_reward": self.bandit_cumulative_reward,
            "rule_cumulative_reward": self.rule_cumulative_reward,
            "regret_vs_logged": self.regret_vs_logged,
            "agreement_rate": self.agreement_rate,
            "action_counts": self.action_counts,
        }


def evaluate_offline(
    logs: list[dict[str, Any]],
    *,
    agent: ContextualBanditAgent,
    feature_names: tuple[str, ...] = FEATURE_NAMES,
) -> OfflineEvaluationResult:
    """
    Replay logged rewards under the IPS-style assumption that logged action reward
    is observed only when the bandit chooses the same action (common offline CB proxy).
    """
    bandit_reward = 0.0
    rule_reward = 0.0
    agreements = 0
    used = 0
    action_counts: dict[str, int] = {action: 0 for action in agent.actions}

    for row in logs:
        features = row.get("features")
        logged_action = row.get("action")
        reward = row.get("reward")
        rule_action = row.get("rule_action") or logged_action
        if reward is None or not isinstance(logged_action, str):
            continue
        vector = _to_vector(features, feature_names, agent.feature_dim)
        if vector is None:
            continue
        choice = agent.choose_action(vector, force_explore=False)
        used += 1
        action_counts[choice.action] = action_counts.get(choice.action, 0) + 1
        if choice.action == logged_action:
            bandit_reward += float(reward)
            agreements += 1
        if isinstance(rule_action, str) and rule_action == logged_action:
            rule_reward += float(reward)
        # Online update after scoring (progressive validation).
        agent.update(vector, logged_action, float(reward))

    agreement_rate = (agreements / used) if used else 0.0
    return OfflineEvaluationResult(
        samples=used,
        bandit_cumulative_reward=bandit_reward,
        rule_cumulative_reward=rule_reward,
        regret_vs_logged=max(0.0, rule_reward - bandit_reward),
        agreement_rate=agreement_rate,
        action_counts=action_counts,
    )


def _to_vector(
    features: object,
    feature_names: tuple[str, ...],
    feature_dim: int,
) -> list[float] | None:
    if isinstance(features, list) and len(features) == feature_dim:
        return [float(v) for v in features]
    if isinstance(features, dict):
        try:
            return [float(features[name]) for name in feature_names]
        except (KeyError, TypeError, ValueError):
            values = [float(v) for v in features.values()]
            if len(values) == feature_dim:
                return values
    return None
