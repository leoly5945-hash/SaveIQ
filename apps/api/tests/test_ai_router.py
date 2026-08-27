from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.settings import Settings
from app.services.llm_intent_contract import LlmIntentParserInput
from app.services.llm_intent_parser import LlmIntentParserService
from app.services.router.ai_router import AiRouter, RouterExecutionResult
from app.services.router.contract import (
    AI_ROUTER_FALLBACK_MODEL,
    IntentComplexity,
    RouterDecision,
    RouteRequest,
)
from app.services.router.metrics import InMemoryMetricsStore, RouterMetrics
from app.services.router.mock_router import MockRouter
from app.services.router.providers.base import ProviderParseResult, ProviderUsage
from app.services.router.providers.mock_provider import MockProvider


class RecordingMockIntentClient:
    def __init__(self, output: Mapping[str, Any]) -> None:
        self.output = output
        self.last_request: LlmIntentParserInput | None = None
        self.last_model: str | None = None

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.last_request = request
        self.last_model = model
        return self.output


class ExplodingAiRouter:
    def execute(self, request: RouteRequest) -> RouterExecutionResult:
        raise RuntimeError("router boom")

    def route(self, request: RouteRequest) -> RouterDecision:
        raise RuntimeError("router boom")


class RecordingProvider:
    name = "openai"

    def __init__(self, payload: dict[str, Any], *, configured: bool = True) -> None:
        self._payload = payload
        self._configured = configured
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> ProviderParseResult:
        self.calls += 1
        return ProviderParseResult(
            provider=self.name,
            model=model,
            payload=self._payload,
            usage=ProviderUsage(prompt_tokens=10, completion_tokens=5),
            latency_ms=12.5,
        )


def _valid_payload() -> dict[str, Any]:
    return {
        "search_query": "wireless earbuds",
        "has_coupon": True,
        "has_cashback": None,
        "freshness": "fresh",
        "sort": "price_asc",
        "confidence": 0.91,
        "reasoning_summary": "Parsed a shopping intent for fresh coupon earbuds.",
        "fallback_reason": None,
    }


def test_mock_router_disabled_returns_default_model() -> None:
    settings = Settings(FEATURE_AI_ROUTER="false", AI_ROUTER_MODE="mock")
    router = MockRouter(settings)

    decision = router.route(RouteRequest(query_text="cheap earbuds"))

    assert decision.selected_model == "intent-parser-v0"
    assert decision.fallback_model == AI_ROUTER_FALLBACK_MODEL
    assert decision.complexity == IntentComplexity.SIMPLE
    assert "disabled" in decision.reason


def test_mock_router_mock_mode_classifies_long_query() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="mock",
        AI_ROUTER_DEFAULT_MODEL="intent-parser-v0",
    )
    router = MockRouter(settings)
    long_query = " ".join(["w"] * 51)

    decision = router.route(RouteRequest(query_text=long_query))

    assert decision.selected_model == "intent-parser-v0"
    assert decision.fallback_model == AI_ROUTER_FALLBACK_MODEL
    assert decision.complexity == IntentComplexity.COMPLEX
    assert "long query" in decision.reason


def test_parser_ignores_router_when_feature_disabled() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="false",
        FEATURE_LLM_INTENT_PARSER="true",
        LLM_INTENT_PARSER_MODE="mock",
        OPENAI_INTENT_MODEL="mock-intent-model",
    )
    client = RecordingMockIntentClient(_valid_payload())
    service = LlmIntentParserService(settings, client)

    result = service.parse("Find fresh wireless earbuds with coupon")

    assert result.fallback_required is False
    assert result.parsed_intent is not None
    assert result.model == "mock-intent-model"
    assert client.last_model == "mock-intent-model"


def test_parser_mock_router_uses_mock_provider_without_keys() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="mock",
        FEATURE_LLM_INTENT_PARSER="false",
        LLM_INTENT_PARSER_MODE="disabled",
    )
    client = RecordingMockIntentClient(_valid_payload())
    metrics = RouterMetrics(InMemoryMetricsStore())
    ai_router = AiRouter(
        settings,
        providers={"mock": MockProvider()},
        metrics=metrics,
    )
    service = LlmIntentParserService(settings, client, router=ai_router, ai_router=ai_router)

    result = service.parse("Find fresh wireless earbuds with coupon")

    assert result.fallback_required is False
    assert result.parsed_intent is not None
    assert result.model == "mock-intent-model"
    assert client.last_request is None
    snapshot = metrics.snapshot()
    assert snapshot["providers"]["mock"]["requests"] == 1


def test_parser_router_exception_falls_back_to_deterministic_model() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="mock",
        FEATURE_LLM_INTENT_PARSER="true",
        LLM_INTENT_PARSER_MODE="mock",
    )
    client = RecordingMockIntentClient(_valid_payload())
    exploding = ExplodingAiRouter()
    service = LlmIntentParserService(
        settings,
        client,
        router=exploding,  # type: ignore[arg-type]
        ai_router=exploding,  # type: ignore[arg-type]
    )

    result = service.parse("Find fresh wireless earbuds with coupon")

    # execute() raises; parser must catch via AiRouter path - currently execute
    # exception is not wrapped. Ensure we handle it.
    assert result.fallback_required is True
    assert client.last_request is None


def test_quality_strategy_routes_complex_to_anthropic_model_name() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="live",
        AI_ROUTER_STRATEGY="quality_optimized",
        OPENAI_API_KEY="test-openai",
        ANTHROPIC_API_KEY="test-anthropic",
    )
    metrics = RouterMetrics(InMemoryMetricsStore())
    openai = RecordingProvider(_valid_payload())
    anthropic = RecordingProvider(_valid_payload())
    anthropic.name = "anthropic"
    router = AiRouter(
        settings,
        providers={"openai": openai, "anthropic": anthropic, "mock": MockProvider()},
        metrics=metrics,
    )
    long_query = " ".join(["w"] * 51)

    decision = router.route(RouteRequest(query_text=long_query))

    assert decision.selected_provider == "anthropic"
    assert decision.complexity == IntentComplexity.COMPLEX


def test_ai_router_fallback_provider_on_primary_failure() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="live",
        AI_ROUTER_STRATEGY="cost_optimized",
        AI_ROUTER_FALLBACK_PROVIDER="mock",
        OPENAI_API_KEY="test-openai",
    )

    class FailingOpenAI:
        name = "openai"

        def is_configured(self) -> bool:
            return True

        def parse_intent(
            self,
            request: LlmIntentParserInput,
            *,
            model: str,
            timeout_seconds: float,
        ):
            raise RuntimeError("boom")

    metrics = RouterMetrics(InMemoryMetricsStore())
    router = AiRouter(
        settings,
        providers={
            "openai": FailingOpenAI(),  # type: ignore[dict-item]
            "mock": MockProvider(),
            "anthropic": RecordingProvider(_valid_payload(), configured=False),
        },
        metrics=metrics,
    )

    result = router.execute(RouteRequest(query_text="fresh earbuds"))

    assert result.fallback_required is False
    assert result.parsed_intent is not None
    assert result.decision.selected_provider == "mock"


def test_admin_router_status_defaults_to_inactive_mock_only() -> None:
    from collections.abc import Generator

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401
    from app.core.settings import get_settings
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()

    def override_db() -> Generator[Session, None, None]:
        yield session

    def override_settings() -> Settings:
        return Settings(FEATURE_AI_ROUTER="false", AI_ROUTER_MODE="disabled")

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = override_settings
    client = TestClient(app)
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        response = client.get("/admin/router-status", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["active"] is False
        assert payload["mode"] == "disabled"
        assert payload["live_ready"] is False
        assert "intent-parser-v0" in payload["available_models"]
        assert "openai_api_key" not in response.text.lower()
        assert "dev-admin-token" not in response.text

        metrics = client.get("/admin/router/metrics", headers=headers)
        assert metrics.status_code == 200
        assert metrics.json()["cache_hits"] == 0

        config = client.get("/admin/router/config", headers=headers)
        assert config.status_code == 200
        assert config.json()["strategy"] in {"cost_optimized", "quality_optimized"}

        updated = client.put(
            "/admin/router/config",
            headers=headers,
            json={"strategy": "quality_optimized"},
        )
        assert updated.status_code == 200
        assert updated.json()["strategy"] == "quality_optimized"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_admin_router_status_reports_active_mock_without_live() -> None:
    from collections.abc import Generator

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401
    from app.core.settings import get_settings
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()

    def override_db() -> Generator[Session, None, None]:
        yield session

    def override_settings() -> Settings:
        return Settings(FEATURE_AI_ROUTER="true", AI_ROUTER_MODE="mock")

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = override_settings
    client = TestClient(app)
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        response = client.get("/admin/router-status", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["active"] is True
        assert payload["mode"] == "mock"
        assert payload["live_ready"] is False
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_fraud_block_skips_primary_provider() -> None:
    from app.services.router.ai_router import AiRouter, get_fraud

    detector = get_fraud()
    previous = detector.enabled
    detector.enabled = True
    detector.block_partner("openai", "unit-test block")
    try:
        settings = Settings(
            FEATURE_AI_ROUTER="true",
            AI_ROUTER_MODE="live",
            FEATURE_CHINESE_LLM_PROVIDERS="false",
            AI_ROUTER_STRATEGY="cost_optimized",
            AI_ROUTER_FALLBACK_PROVIDER="mock",
        )
        openai = RecordingProvider(_valid_payload())
        mock = RecordingProvider(_valid_payload())
        mock.name = "mock"
        router = AiRouter(
            settings,
            providers={"openai": openai, "mock": mock},
            metrics=RouterMetrics(InMemoryMetricsStore()),
        )
        result = router.execute(RouteRequest(query_text="cheap earbuds", user_id="u-fraud"))
        assert result.decision.selected_provider == "mock"
        assert openai.calls == 0
        assert mock.calls == 1
    finally:
        detector.unblock_partner("openai")
        detector.enabled = previous


def test_attribution_records_provider_touch_on_success() -> None:
    from app.services.router.ai_router import AiRouter, get_attribution

    tracker = get_attribution()
    previous = tracker.enabled
    tracker.enabled = True
    before = len(tracker._touches)
    try:
        settings = Settings(
            FEATURE_AI_ROUTER="true",
            AI_ROUTER_MODE="mock",
        )
        router = AiRouter(
            settings,
            providers={"mock": MockProvider()},
            metrics=RouterMetrics(InMemoryMetricsStore()),
        )
        result = router.execute(RouteRequest(query_text="cheap earbuds", user_id="u-attr"))
        assert result.fallback_required is False
        assert len(tracker._touches) == before + 1
        assert tracker._touches[-1].user_id == "u-attr"
        assert tracker._touches[-1].affiliate_id == "mock"
    finally:
        tracker.enabled = previous
