"""Bandit router service: logging-first integration with multi-policy Gate 9 agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.services.bandit.agent import BanditChoice, ContextualBanditAgent
from app.services.bandit.bayesian import tune_reward_hyperparameters
from app.services.bandit.features import (
    FEATURE_NAMES,
    BanditContext,
    build_feature_vector,
    context_metadata,
    features_as_dict,
)
from app.services.bandit.neural import NeuralBanditAgent
from app.services.bandit.offline import evaluate_offline
from app.services.bandit.repository import BanditLogRepository
from app.services.bandit.reward import RewardBreakdown, calculate_reward
from app.services.bandit.rlhf import RlhfPolicyAgent
from app.services.eval.benchmark import run_router_benchmark
from app.services.router.contract import IntentComplexity

logger = logging.getLogger(__name__)

DEFAULT_ACTIONS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "mock",
    "deepseek",
    "qwen",
    "ernie",
)
PolicyName = Literal["rule", "linucb", "neural", "rlhf"]


@dataclass(frozen=True)
class BanditRoutingDecision:
    """Result of consulting the bandit before provider invocation."""

    rule_action: str
    bandit_action: str
    selected_action: str
    applied: bool
    explored: bool
    ready: bool
    mode: str
    features: dict[str, float]
    feature_vector: list[float]
    scores: dict[str, float]
    reason: str
    policy: str = "linucb"


class BanditRouterService:
    """Gate 7/9 bandit controller. Default mode never changes live routing."""

    def __init__(
        self,
        settings: Settings,
        *,
        agent: ContextualBanditAgent | None = None,
        repository: BanditLogRepository | None = None,
        neural: NeuralBanditAgent | None = None,
        rlhf: RlhfPolicyAgent | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository or BanditLogRepository()
        feature_dim = len(FEATURE_NAMES)
        self._agent = agent or ContextualBanditAgent(
            actions=DEFAULT_ACTIONS,
            feature_dim=feature_dim,
            alpha=settings.bandit_alpha,
            epsilon=settings.bandit_epsilon,
            min_samples_ready=settings.bandit_min_samples_ready,
        )
        self._neural = neural or NeuralBanditAgent(
            actions=DEFAULT_ACTIONS,
            feature_dim=feature_dim,
            epsilon=settings.bandit_epsilon,
            min_samples_ready=max(settings.bandit_min_samples_ready, 25),
        )
        self._rlhf = rlhf or RlhfPolicyAgent(
            actions=DEFAULT_ACTIONS,
            feature_dim=feature_dim,
            min_samples_ready=max(settings.bandit_min_samples_ready, 30),
        )
        self._policy: PolicyName = settings.bandit_policy
        self._last_offline_metrics: dict[str, Any] = {}
        self._last_benchmark: dict[str, Any] = {}
        self._last_tuning: dict[str, Any] = {}

    @property
    def agent(self) -> ContextualBanditAgent:
        return self._agent

    def enabled(self) -> bool:
        from app.services.canary.effective import effective_bandit_mode, is_feature_active

        if not is_feature_active("bandit", settings=self._settings):
            return False
        return effective_bandit_mode(self._settings) in {"logging", "active"}

    def active_policy(self) -> PolicyName:
        return self._policy

    def switch_policy(self, policy: str) -> dict[str, Any]:
        normalized = policy.strip().lower()
        if normalized not in {"rule", "linucb", "neural", "rlhf"}:
            raise ValueError("policy must be one of: rule, linucb, neural, rlhf")
        if normalized == "neural" and not self._settings.feature_neural_bandit:
            raise ValueError("FEATURE_NEURAL_BANDIT is disabled")
        if normalized == "rlhf" and not self._settings.feature_rlhf_router:
            raise ValueError("FEATURE_RLHF_ROUTER is disabled")
        self._policy = normalized  # type: ignore[assignment]
        return {"policy": self._policy, "feature_enabled": self._settings.feature_bandit_router}

    def decide(
        self,
        *,
        query_text: str,
        intent_type: str,
        market: str,
        user_id: str | None,
        rule_action: str,
        available_actions: list[str],
        complexity: IntentComplexity,
        personalization_features: dict[str, float] | None = None,
    ) -> BanditRoutingDecision:
        context = BanditContext(
            query_text=query_text,
            intent_type=intent_type,
            market=market,
            user_id=user_id,
            personalization=personalization_features or {},
        )
        vector = build_feature_vector(context)
        features = features_as_dict(vector)
        mode = self._settings.bandit_router_mode
        policy = self._policy

        if not self.enabled() or policy == "rule":
            return BanditRoutingDecision(
                rule_action=rule_action,
                bandit_action=rule_action,
                selected_action=rule_action,
                applied=False,
                explored=False,
                ready=False,
                mode="disabled" if not self.enabled() else mode,
                features=features,
                feature_vector=vector,
                scores={},
                reason="bandit disabled" if not self.enabled() else "policy=rule",
                policy=policy,
            )

        candidates = [action for action in available_actions if action in DEFAULT_ACTIONS]
        if not candidates:
            candidates = [rule_action]

        choice_action = rule_action
        scores: dict[str, float] = {}
        explored = False
        ready = False
        choice_reason = "fallback rule"

        if policy == "neural" and self._settings.feature_neural_bandit:
            neural_choice = self._neural.choose_action(vector, available_actions=candidates)
            choice_action = neural_choice.action
            scores = neural_choice.scores
            explored = neural_choice.explored
            ready = neural_choice.ready
            choice_reason = neural_choice.reason
            if not ready:
                fallback_choice = self._agent.choose_action(
                    vector, available_actions=candidates, force_explore=False
                )
                choice_action = fallback_choice.action
                scores = fallback_choice.scores
                choice_reason = f"neural not ready; linucb chose {choice_action}"
                ready = self._agent.ready
        elif policy == "rlhf" and self._settings.feature_rlhf_router:
            rlhf_choice = self._rlhf.choose_action(vector, available_actions=candidates)
            choice_action = rlhf_choice.action
            scores = rlhf_choice.probs
            explored = rlhf_choice.explored
            ready = rlhf_choice.ready
            choice_reason = rlhf_choice.reason
            if not ready:
                fallback_choice = self._agent.choose_action(
                    vector, available_actions=candidates, force_explore=False
                )
                choice_action = fallback_choice.action
                scores = fallback_choice.scores
                choice_reason = f"rlhf not ready; linucb chose {choice_action}"
                ready = self._agent.ready
        else:
            linucb_choice: BanditChoice = self._agent.choose_action(
                vector,
                available_actions=candidates,
            )
            choice_action = linucb_choice.action
            scores = linucb_choice.scores
            explored = linucb_choice.explored
            ready = linucb_choice.ready
            choice_reason = linucb_choice.reason
            policy = "linucb"

        applied = False
        selected = rule_action
        reason = f"logging-only; {policy} suggested {choice_action}"
        if mode == "active":
            if ready:
                selected = choice_action
                applied = True
                reason = f"active {policy} selected {choice_action} ({choice_reason})"
            else:
                reason = f"active {policy} not ready; using rule {rule_action} ({choice_reason})"

        logger.info(
            "bandit decide mode=%s policy=%s complexity=%s rule=%s bandit=%s selected=%s",
            mode,
            policy,
            complexity.value,
            rule_action,
            choice_action,
            selected,
        )
        return BanditRoutingDecision(
            rule_action=rule_action,
            bandit_action=choice_action,
            selected_action=selected,
            applied=applied,
            explored=explored,
            ready=ready,
            mode=mode,
            features=features,
            feature_vector=vector,
            scores=scores,
            reason=reason,
            policy=policy,
        )

    def observe(
        self,
        decision: BanditRoutingDecision,
        *,
        action: str,
        confidence: float | None,
        estimated_cost_usd: float | None,
        latency_ms: float | None,
        success: bool,
        user_satisfaction: float | None = None,
        user_id: str | None = None,
        query_text: str | None = None,
        intent_type: str | None = None,
        market: str | None = None,
        db: Session | None = None,
    ) -> RewardBreakdown:
        reward = calculate_reward(
            confidence=confidence,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
            success=success,
            user_satisfaction=user_satisfaction,
            alpha=self._settings.bandit_reward_alpha,
            beta=self._settings.bandit_reward_beta,
            gamma=self._settings.bandit_reward_gamma,
            delta=self._settings.bandit_reward_delta,
        )
        if self.enabled():
            self._agent.update(decision.feature_vector, action, reward.reward)
            if self._settings.feature_neural_bandit:
                self._neural.update(decision.feature_vector, action, reward.reward)
            if self._settings.feature_rlhf_router:
                self._rlhf.update(decision.feature_vector, action, reward.reward)

        metadata: dict[str, Any] = {
            "scores": decision.scores,
            "reason": decision.reason,
            "policy": decision.policy,
            "reward_breakdown": {
                "quality": reward.quality,
                "cost_term": reward.cost_term,
                "latency_term": reward.latency_term,
                "user_satisfaction": reward.user_satisfaction,
            },
            "context": context_metadata(
                BanditContext(
                    query_text=query_text or "",
                    intent_type=intent_type or "recommendation",
                    market=market or "CA",
                    user_id=user_id,
                )
            )
            if query_text
            else {},
        }
        if self.enabled():
            self._repository.insert_log(
                features=decision.features,
                action=action,
                reward=reward.reward,
                user_id=user_id,
                rule_action=decision.rule_action,
                bandit_action=decision.bandit_action,
                mode=decision.mode,
                applied=decision.applied,
                explored=decision.explored,
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
                confidence=confidence,
                metadata=metadata,
                db=db,
            )
        return reward

    def train_from_logs(self, *, limit: int = 5000, db: Session | None = None) -> dict[str, Any]:
        logs = self._repository.fetch_training_logs(limit=limit, db=db)
        trained = self._agent.train_offline(logs)
        for row in logs:
            features_obj = row.get("features")
            action = row.get("action")
            reward = row.get("reward")
            if not isinstance(action, str) or reward is None:
                continue
            typed_features: list[float] | dict[str, float]
            if isinstance(features_obj, list):
                typed_features = [float(item) for item in features_obj]
            elif isinstance(features_obj, dict):
                typed_features = {str(key): float(value) for key, value in features_obj.items()}
            else:
                continue
            vector = self._agent._features_to_vector(typed_features)  # noqa: SLF001
            if self._settings.feature_neural_bandit:
                self._neural.update(vector, action, float(reward))
            if self._settings.feature_rlhf_router:
                self._rlhf.update(vector, action, float(reward))
        offline = evaluate_offline(
            logs,
            agent=ContextualBanditAgent(
                actions=self._agent.actions,
                feature_dim=self._agent.feature_dim,
                alpha=self._agent.alpha,
                epsilon=0.0,
                min_samples_ready=self._agent.min_samples_ready,
            ),
        )
        self._last_offline_metrics = offline.as_dict()
        tuning: dict[str, Any] = {}
        if self._settings.feature_bayesian_tuning:
            result = tune_reward_hyperparameters(
                [{"reward": row.get("reward"), "reward_breakdown": {}} for row in logs]
            )
            self._last_tuning = result.as_dict()
            tuning = self._last_tuning
        return {
            "trained": trained,
            "agent": self._agent.status(),
            "neural": self._neural.status(),
            "rlhf": self._rlhf.status(),
            "offline_evaluation": self._last_offline_metrics,
            "bayesian_tuning": tuning,
        }

    def run_benchmark(self, *, limit: int = 5000, db: Session | None = None) -> dict[str, Any]:
        logs = self._repository.fetch_training_logs(limit=limit, db=db)
        self._last_benchmark = run_router_benchmark(logs or None)
        return self._last_benchmark

    def benchmark_results(self) -> dict[str, Any]:
        if not self._last_benchmark:
            self._last_benchmark = run_router_benchmark()
        return self._last_benchmark

    def reset(self) -> dict[str, Any]:
        self._agent.reset()
        self._neural.reset()
        self._rlhf.reset()
        self._last_offline_metrics = {}
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "feature_enabled": self._settings.feature_bandit_router,
            "mode": self._settings.bandit_router_mode,
            "policy": self._policy,
            "active": self.enabled(),
            "logging_only": self.enabled() and self._settings.bandit_router_mode == "logging",
            "controls_routing": (
                self.enabled()
                and self._settings.bandit_router_mode == "active"
                and (
                    self._agent.ready
                    if self._policy == "linucb"
                    else self._neural.ready
                    if self._policy == "neural"
                    else self._rlhf.ready
                    if self._policy == "rlhf"
                    else False
                )
            ),
            "features": list(FEATURE_NAMES),
            "agent": self._agent.status(),
            "neural": self._neural.status(),
            "rlhf": self._rlhf.status(),
            "flags": {
                "neural": self._settings.feature_neural_bandit,
                "rlhf": self._settings.feature_rlhf_router,
                "bayesian_tuning": self._settings.feature_bayesian_tuning,
                "chinese_providers": self._settings.feature_chinese_llm_providers,
            },
            "reward_weights": {
                "alpha": self._settings.bandit_reward_alpha,
                "beta": self._settings.bandit_reward_beta,
                "gamma": self._settings.bandit_reward_gamma,
                "delta": self._settings.bandit_reward_delta,
            },
            "log_count": self._repository.count_logs(),
            "offline_evaluation": self._last_offline_metrics,
            "bayesian_tuning": self._last_tuning,
        }

    def public_status(self) -> dict[str, Any]:
        full = self.status()
        return {
            "active": full["active"],
            "mode": full["mode"],
            "policy": full["policy"],
            "logging_only": full["logging_only"],
            "controls_routing": full["controls_routing"],
            "algorithm": full["agent"].get("algorithm"),
            "ready": full["agent"].get("ready"),
            "sample_count": full["agent"].get("sample_count"),
        }

    def metrics(self) -> dict[str, Any]:
        agent = self._agent.status()
        return {
            "policy": self._policy,
            "cumulative_reward": agent["cumulative_reward"],
            "sample_count": agent["sample_count"],
            "action_counts": agent["action_counts"],
            "ready": agent["ready"],
            "neural": self._neural.status(),
            "rlhf": self._rlhf.status(),
            "offline_evaluation": self._last_offline_metrics,
            "log_count": self._repository.count_logs(),
        }


_bandit_singleton: BanditRouterService | None = None


def build_bandit_router_service(
    settings: Settings,
    *,
    repository: BanditLogRepository | None = None,
    agent: ContextualBanditAgent | None = None,
    reuse_singleton: bool = True,
) -> BanditRouterService:
    global _bandit_singleton
    if reuse_singleton and _bandit_singleton is not None and agent is None and repository is None:
        _bandit_singleton._settings = settings  # noqa: SLF001
        return _bandit_singleton
    service = BanditRouterService(settings, agent=agent, repository=repository)
    if reuse_singleton and agent is None and repository is None:
        _bandit_singleton = service
    return service


def reset_bandit_singleton() -> None:
    global _bandit_singleton
    _bandit_singleton = None
