"""Production AI router (Gate 6B) with providers, cache, fallback, and cost logs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.settings import Settings
from app.services.bandit.service import (
    BanditRouterService,
    BanditRoutingDecision,
    build_bandit_router_service,
)
from app.services.llm_intent_contract import LlmIntentParserInput, LlmParsedIntent
from app.services.router.cache import RouterIntentCache
from app.services.router.contract import (
    AI_ROUTER_FALLBACK_MODEL,
    IntentComplexity,
    RouterDecision,
    RouteRequest,
    classify_complexity,
)
from app.services.router.cost import estimate_cost_usd
from app.services.router.metrics import RouterMetrics
from app.services.router.providers.anthropic_provider import AnthropicProvider
from app.services.router.providers.base import BaseLLMProvider, ProviderParseResult
from app.services.router.providers.deepseek_provider import DeepSeekProvider
from app.services.router.providers.ernie_provider import ErnieProvider
from app.services.router.providers.mock_provider import MockProvider
from app.services.router.providers.openai_provider import OpenAIProvider
from app.services.router.providers.qwen_provider import QwenProvider
from app.services.router.redis_client import create_redis_client

logger = logging.getLogger(__name__)

MIN_ROUTER_INTENT_CONFIDENCE = 0.60


@dataclass(frozen=True)
class RouterExecutionResult:
    decision: RouterDecision
    parsed_intent: LlmParsedIntent | None
    fallback_required: bool
    fallback_reason: str | None


class AiRouter:
    """Selects and invokes intent-parser providers behind FEATURE_AI_ROUTER."""

    def __init__(
        self,
        settings: Settings,
        *,
        providers: dict[str, BaseLLMProvider] | None = None,
        cache: RouterIntentCache | None = None,
        metrics: RouterMetrics | None = None,
        bandit: BanditRouterService | None = None,
    ) -> None:
        self._settings = settings
        redis_client = create_redis_client(settings.redis_url)
        self._metrics = metrics or RouterMetrics(redis_client)
        self._cache = cache or RouterIntentCache(
            redis_client,
            enabled=settings.ai_router_cache_enabled,
            ttl_seconds=settings.ai_router_cache_ttl_seconds,
        )
        self._providers = providers or {
            "mock": MockProvider(),
            "openai": OpenAIProvider(settings.openai_api_key),
            "anthropic": AnthropicProvider(settings.anthropic_api_key),
            "deepseek": DeepSeekProvider(settings.deepseek_api_key),
            "qwen": QwenProvider(settings.dashscope_api_key),
            "ernie": ErnieProvider(settings.baidu_api_key, settings.baidu_secret_key),
        }
        self._bandit = bandit or build_bandit_router_service(settings)

    def route(self, request: RouteRequest) -> RouterDecision:
        """Compatibility helper used by Gate 6A-style callers."""
        complexity = classify_complexity(request.query_text)
        if not self._router_active():
            return RouterDecision(
                selected_model=self._settings.ai_router_default_model or AI_ROUTER_FALLBACK_MODEL,
                selected_provider="none",
                reason="AI router disabled; using default model",
                fallback_model=AI_ROUTER_FALLBACK_MODEL,
                fallback_provider="none",
                complexity=complexity,
            )
        primary, fallback = self._select_providers(complexity)
        primary_model = self._model_for_provider(primary)
        fallback_model = (
            self._model_for_provider(fallback) if fallback else AI_ROUTER_FALLBACK_MODEL
        )
        return RouterDecision(
            selected_model=primary_model,
            selected_provider=primary,
            reason=f"{self._active_strategy()} routed {complexity.value} to {primary}",
            fallback_model=fallback_model,
            fallback_provider=fallback or "none",
            complexity=complexity,
        )

    def execute(self, request: RouteRequest) -> RouterExecutionResult:
        complexity = classify_complexity(request.query_text)
        if not self._router_active():
            decision = self.route(request)
            return RouterExecutionResult(
                decision=decision,
                parsed_intent=None,
                fallback_required=True,
                fallback_reason="AI router disabled",
            )

        cache_key = self._cache.make_key(
            query_text=request.query_text,
            market=request.market,
            intent_type=request.intent_type,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                parsed = LlmParsedIntent.model_validate(cached.get("payload"))
            except ValidationError:
                parsed = None
            if parsed is not None and parsed.confidence >= MIN_ROUTER_INTENT_CONFIDENCE:
                provider = str(cached.get("provider") or "cache")
                model = str(cached.get("model") or AI_ROUTER_FALLBACK_MODEL)
                decision = RouterDecision(
                    selected_model=model,
                    selected_provider=provider,
                    reason="cache hit",
                    fallback_model=AI_ROUTER_FALLBACK_MODEL,
                    fallback_provider="none",
                    complexity=complexity,
                    cache_hit=True,
                    latency_ms=0.0,
                    estimated_cost_usd=0.0,
                )
                self._metrics.record_request(
                    provider=provider,
                    prompt_tokens=0,
                    completion_tokens=0,
                    estimated_cost_usd=0.0,
                    latency_ms=0.0,
                    cache_hit=True,
                )
                logger.info(
                    "AI router cache hit provider=%s model=%s",
                    provider,
                    model,
                )
                return RouterExecutionResult(
                    decision=decision,
                    parsed_intent=parsed,
                    fallback_required=False,
                    fallback_reason=None,
                )

        primary, fallback = self._select_providers(complexity)
        bandit_decision = self._consult_bandit(request, complexity, primary)
        if bandit_decision.applied and bandit_decision.selected_action != primary:
            # Keep original primary as fallback when bandit overrides.
            if fallback is None and primary != bandit_decision.selected_action:
                fallback = primary
            primary = bandit_decision.selected_action
        try:
            result = self._invoke_provider(primary, request)
            return self._accept_provider_result(
                result,
                request=request,
                complexity=complexity,
                cache_key=cache_key,
                fallback_provider=fallback or "none",
                bandit_decision=bandit_decision,
            )
        except Exception as primary_exc:  # noqa: BLE001
            logger.warning(
                "AI router primary provider failed provider=%s (%s)",
                primary,
                primary_exc.__class__.__name__,
            )
            self._metrics.record_request(
                provider=primary,
                prompt_tokens=0,
                completion_tokens=0,
                estimated_cost_usd=0.0,
                latency_ms=0.0,
                error=True,
                cache_hit=False,
            )
            self._observe_bandit(
                bandit_decision,
                request=request,
                action=primary,
                confidence=None,
                estimated_cost_usd=None,
                latency_ms=None,
                success=False,
            )
            if fallback and fallback != primary:
                try:
                    result = self._invoke_provider(fallback, request)
                    return self._accept_provider_result(
                        result,
                        request=request,
                        complexity=complexity,
                        cache_key=cache_key,
                        fallback_provider="none",
                        reason_prefix=f"fallback after {primary} failure; ",
                        bandit_decision=bandit_decision,
                    )
                except Exception as fallback_exc:  # noqa: BLE001
                    logger.warning(
                        "AI router fallback provider failed provider=%s (%s)",
                        fallback,
                        fallback_exc.__class__.__name__,
                    )
                    self._metrics.record_request(
                        provider=fallback,
                        prompt_tokens=0,
                        completion_tokens=0,
                        estimated_cost_usd=0.0,
                        latency_ms=0.0,
                        error=True,
                        cache_hit=False,
                    )
                    self._observe_bandit(
                        bandit_decision,
                        request=request,
                        action=fallback,
                        confidence=None,
                        estimated_cost_usd=None,
                        latency_ms=None,
                        success=False,
                    )

        decision = RouterDecision(
            selected_model=AI_ROUTER_FALLBACK_MODEL,
            selected_provider="none",
            reason="all providers failed; using deterministic parser",
            fallback_model=AI_ROUTER_FALLBACK_MODEL,
            fallback_provider="none",
            complexity=complexity,
            cache_hit=False,
        )
        return RouterExecutionResult(
            decision=decision,
            parsed_intent=None,
            fallback_required=True,
            fallback_reason="router providers failed",
        )

    def status(self) -> dict[str, Any]:
        # Global status stays env-flag based so production smoke can assert flags off
        # while canary may still enable features for a sticky cohort.
        live_ready = self._settings.feature_ai_router and self._settings.ai_router_mode == "live"
        configured = {name: provider.is_configured() for name, provider in self._providers.items()}
        return {
            "active": self._settings.feature_ai_router
            and self._settings.ai_router_mode in {"mock", "live"},
            "mode": self._settings.ai_router_mode,
            "strategy": self._active_strategy(),
            "default_model": self._settings.ai_router_default_model,
            "live_ready": live_ready
            and any(
                configured.get(name)
                for name in ("openai", "anthropic", "deepseek", "qwen", "ernie")
            ),
            "available_models": list(
                {
                    AI_ROUTER_FALLBACK_MODEL,
                    self._settings.openai_intent_model,
                    self._settings.anthropic_intent_model,
                    self._settings.deepseek_intent_model,
                    self._settings.qwen_intent_model,
                    self._settings.ernie_intent_model,
                    "mock-intent-model",
                }
            ),
            "providers_configured": configured,
            "chinese_providers_enabled": self._settings.feature_chinese_llm_providers,
            "cache_enabled": self._cache.enabled,
            "fallback_provider": self._settings.ai_router_fallback_provider,
            "bandit": self._bandit.public_status(),
            "request_router_active": self._router_active(),
            "request_chinese_active": self._chinese_active(),
            "abtest": self._ab_group_config(),
        }

    def metrics_snapshot(self) -> dict[str, Any]:
        return self._metrics.snapshot()

    def get_config(self) -> dict[str, Any]:
        return {
            "strategy": self._active_strategy(),
            "mode": self._settings.ai_router_mode,
            "fallback_provider": self._settings.ai_router_fallback_provider,
            "cache_enabled": self._settings.ai_router_cache_enabled,
            "cache_ttl_seconds": self._settings.ai_router_cache_ttl_seconds,
            "feature_enabled": self._settings.feature_ai_router,
        }

    def set_strategy(self, strategy: str) -> dict[str, Any]:
        normalized = strategy.strip().lower()
        if normalized not in {"cost_optimized", "quality_optimized"}:
            raise ValueError("strategy must be cost_optimized or quality_optimized")
        self._metrics.set_strategy_override(normalized)
        return self.get_config()

    def _active_strategy(self) -> str:
        override = self._metrics.get_strategy_override()
        if override in {"cost_optimized", "quality_optimized"}:
            return override
        return self._settings.ai_router_strategy

    def _select_providers(self, complexity: IntentComplexity) -> tuple[str, str | None]:
        if self._effective_mode() == "mock":
            return "mock", None

        strategy = self._active_strategy()
        chinese = self._chinese_active()
        if strategy == "quality_optimized":
            if complexity == IntentComplexity.COMPLEX:
                primary = "qwen" if chinese else "anthropic"
            else:
                primary = "openai"
        else:
            # cost_optimized: prefer DeepSeek when Chinese providers are enabled.
            primary = "deepseek" if chinese else "openai"

        configured_primary = primary if self._provider_ready(primary) else None
        if configured_primary is None:
            # Mode is live here (mock returns earlier). Prefer any configured provider.
            candidates = (
                "deepseek",
                "qwen",
                "ernie",
                "openai",
                "anthropic",
                "mock",
            )
            for candidate in candidates:
                if self._provider_ready(candidate):
                    configured_primary = candidate
                    break
            if configured_primary is None:
                return "mock", None

        fallback_setting = self._settings.ai_router_fallback_provider
        fallback: str | None = None
        if fallback_setting != "none" and fallback_setting != configured_primary:
            if self._provider_ready(fallback_setting):
                fallback = fallback_setting
        return configured_primary, fallback

    def _consult_bandit(
        self,
        request: RouteRequest,
        complexity: IntentComplexity,
        rule_action: str,
    ) -> BanditRoutingDecision:
        available = [name for name, provider in self._providers.items() if provider.is_configured()]
        if not available:
            available = [rule_action]
        from app.services.canary.effective import is_feature_active

        personalization_features: dict[str, float] = {}
        if is_feature_active("personalization", settings=self._settings) and request.user_id:
            try:
                from app.services.user.profile import build_user_profile_service

                profile = build_user_profile_service(self._settings).get_profile(
                    request.user_id,
                    create_if_missing=True,
                )
                if profile is not None and profile.personalization_active:
                    personalization_features = profile.bandit_features()
            except Exception:  # noqa: BLE001
                logger.exception("Personalization profile load failed; continuing without it")
        return self._bandit.decide(
            query_text=request.query_text,
            intent_type=request.intent_type,
            market=request.market,
            user_id=request.user_id,
            rule_action=rule_action,
            available_actions=available,
            complexity=complexity,
            personalization_features=personalization_features,
        )

    def _observe_bandit(
        self,
        decision: BanditRoutingDecision,
        *,
        request: RouteRequest,
        action: str,
        confidence: float | None,
        estimated_cost_usd: float | None,
        latency_ms: float | None,
        success: bool,
    ) -> None:
        try:
            self._bandit.observe(
                decision,
                action=action,
                confidence=confidence,
                estimated_cost_usd=estimated_cost_usd,
                latency_ms=latency_ms,
                success=success,
                user_id=request.user_id,
                query_text=request.query_text,
                intent_type=request.intent_type,
                market=request.market,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Bandit observe failed")

    def _provider_ready(self, name: str) -> bool:
        chinese = {"deepseek", "qwen", "ernie"}
        if name in chinese and not self._chinese_active():
            return False
        provider = self._providers.get(name)
        return provider is not None and provider.is_configured()

    def _effective_mode(self) -> str:
        from app.services.canary.effective import effective_ai_router_mode

        return effective_ai_router_mode(self._settings)

    def _router_active(self) -> bool:
        return self._effective_mode() in {"mock", "live"}

    def _chinese_active(self) -> bool:
        from app.services.canary.effective import is_feature_active

        return is_feature_active("llm_cn", settings=self._settings)

    def _ab_group_config(self) -> dict[str, object]:
        """Expose active A/B overrides for status/debug (Gate 10D)."""
        from app.services.abtest.context import get_ab_group, get_ab_overrides

        overrides = get_ab_overrides() or {}
        return {"group": get_ab_group(), "overrides": overrides}

    def _model_for_provider(self, provider: str) -> str:
        if provider == "openai":
            return self._settings.openai_intent_model
        if provider == "anthropic":
            return self._settings.anthropic_intent_model
        if provider == "deepseek":
            return self._settings.deepseek_intent_model
        if provider == "qwen":
            return self._settings.qwen_intent_model
        if provider == "ernie":
            return self._settings.ernie_intent_model
        if provider == "mock":
            return "mock-intent-model"
        return AI_ROUTER_FALLBACK_MODEL

    def _timeout_for_provider(self, provider: str) -> float:
        if provider == "anthropic":
            return self._settings.anthropic_intent_timeout_seconds
        if provider == "deepseek":
            return self._settings.deepseek_intent_timeout_seconds
        if provider == "qwen":
            return self._settings.qwen_intent_timeout_seconds
        if provider == "ernie":
            return self._settings.ernie_intent_timeout_seconds
        return self._settings.openai_intent_timeout_seconds

    def _invoke_provider(self, provider_name: str, request: RouteRequest) -> ProviderParseResult:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise RuntimeError(f"Unknown provider: {provider_name}")
        if not provider.is_configured():
            raise RuntimeError(f"Provider not configured: {provider_name}")
        parser_input = LlmIntentParserInput(
            raw_intent=request.query_text,
            market=request.market,
        )
        return provider.parse_intent(
            parser_input,
            model=self._model_for_provider(provider_name),
            timeout_seconds=self._timeout_for_provider(provider_name),
        )

    def _accept_provider_result(
        self,
        result: ProviderParseResult,
        *,
        request: RouteRequest,
        complexity: IntentComplexity,
        cache_key: str,
        fallback_provider: str,
        reason_prefix: str = "",
        bandit_decision: BanditRoutingDecision | None = None,
    ) -> RouterExecutionResult:
        try:
            parsed = LlmParsedIntent.model_validate(result.payload)
        except ValidationError as exc:
            cost = estimate_cost_usd(
                provider=result.provider,
                model=result.model,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
            )
            self._metrics.record_request(
                provider=result.provider,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                estimated_cost_usd=cost.estimated_cost_usd,
                latency_ms=result.latency_ms,
                error=True,
                cache_hit=False,
            )
            logger.info(
                "AI router cost provider=%s model=%s tokens=%s cost_usd=%s",
                result.provider,
                result.model,
                result.usage.total_tokens,
                cost.estimated_cost_usd,
            )
            if bandit_decision is not None:
                self._observe_bandit(
                    bandit_decision,
                    request=request,
                    action=result.provider,
                    confidence=None,
                    estimated_cost_usd=cost.estimated_cost_usd,
                    latency_ms=result.latency_ms,
                    success=False,
                )
            raise RuntimeError("provider output failed schema validation") from exc

        cost = estimate_cost_usd(
            provider=result.provider,
            model=result.model,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
        )
        logger.info(
            "AI router cost provider=%s model=%s prompt_tokens=%s completion_tokens=%s "
            "cost_usd=%s latency_ms=%.2f",
            result.provider,
            result.model,
            result.usage.prompt_tokens,
            result.usage.completion_tokens,
            cost.estimated_cost_usd,
            result.latency_ms,
        )
        self._metrics.record_request(
            provider=result.provider,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            estimated_cost_usd=cost.estimated_cost_usd,
            latency_ms=result.latency_ms,
            cache_hit=False,
        )

        if parsed.confidence < MIN_ROUTER_INTENT_CONFIDENCE:
            decision = RouterDecision(
                selected_model=result.model,
                selected_provider=result.provider,
                reason=f"{reason_prefix}low confidence from {result.provider}",
                fallback_model=AI_ROUTER_FALLBACK_MODEL,
                fallback_provider=fallback_provider,
                complexity=complexity,
                cache_hit=False,
                latency_ms=result.latency_ms,
                estimated_cost_usd=cost.estimated_cost_usd,
            )
            if bandit_decision is not None:
                self._observe_bandit(
                    bandit_decision,
                    request=request,
                    action=result.provider,
                    confidence=parsed.confidence,
                    estimated_cost_usd=cost.estimated_cost_usd,
                    latency_ms=result.latency_ms,
                    success=False,
                )
            return RouterExecutionResult(
                decision=decision,
                parsed_intent=parsed,
                fallback_required=True,
                fallback_reason="router confidence below 0.60",
            )

        self._cache.set(
            cache_key,
            {
                "provider": result.provider,
                "model": result.model,
                "payload": result.payload,
            },
        )
        bandit_note = ""
        if bandit_decision is not None and bandit_decision.mode != "disabled":
            bandit_note = f"; bandit={bandit_decision.reason}"
        decision = RouterDecision(
            selected_model=result.model,
            selected_provider=result.provider,
            reason=(
                f"{reason_prefix}{self._active_strategy()} selected {result.provider} "
                f"for {complexity.value}{bandit_note}"
            )[:240],
            fallback_model=AI_ROUTER_FALLBACK_MODEL,
            fallback_provider=fallback_provider,
            complexity=complexity,
            cache_hit=False,
            latency_ms=result.latency_ms,
            estimated_cost_usd=cost.estimated_cost_usd,
        )
        if bandit_decision is not None:
            self._observe_bandit(
                bandit_decision,
                request=request,
                action=result.provider,
                confidence=parsed.confidence,
                estimated_cost_usd=cost.estimated_cost_usd,
                latency_ms=result.latency_ms,
                success=True,
            )
        return RouterExecutionResult(
            decision=decision,
            parsed_intent=parsed,
            fallback_required=False,
            fallback_reason=None,
        )


def build_ai_router(settings: Settings) -> AiRouter:
    return AiRouter(settings)
