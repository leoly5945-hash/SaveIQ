from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.settings import Settings
from app.services.llm_intent_contract import LlmIntentParserInput
from app.services.llm_intent_parser import LlmIntentParserService
from app.services.router.contract import AI_ROUTER_FALLBACK_MODEL, IntentComplexity, RouteRequest
from app.services.router.mock_router import MockRouter


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


class ExplodingRouter:
    def route(self, request: RouteRequest) -> object:
        raise RuntimeError("router boom")


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
    client = RecordingMockIntentClient(
        {
            "search_query": "wireless earbuds",
            "has_coupon": True,
            "has_cashback": None,
            "freshness": "fresh",
            "sort": "price_asc",
            "confidence": 0.91,
            "reasoning_summary": "Parsed a shopping intent for fresh coupon earbuds.",
        }
    )
    service = LlmIntentParserService(settings, client)

    result = service.parse("Find fresh wireless earbuds with coupon")

    assert result.fallback_required is False
    assert result.parsed_intent is not None
    assert result.model == "mock-intent-model"
    assert client.last_model == "mock-intent-model"


def test_parser_router_selects_fallback_and_skips_llm_client() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="mock",
        FEATURE_LLM_INTENT_PARSER="true",
        LLM_INTENT_PARSER_MODE="mock",
        OPENAI_INTENT_MODEL="mock-intent-model",
    )
    client = RecordingMockIntentClient(
        {
            "search_query": "wireless earbuds",
            "has_coupon": True,
            "has_cashback": None,
            "freshness": "fresh",
            "sort": "price_asc",
            "confidence": 0.91,
            "reasoning_summary": "should not be used",
        }
    )
    service = LlmIntentParserService(settings, client)

    result = service.parse("Find fresh wireless earbuds with coupon")

    assert result.fallback_required is True
    assert result.fallback_reason == "router selected intent-parser-v0"
    assert result.model == "intent-parser-v0"
    assert result.parsed_intent is None
    assert client.last_request is None


def test_parser_router_exception_falls_back_to_deterministic_model() -> None:
    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="mock",
        FEATURE_LLM_INTENT_PARSER="true",
        LLM_INTENT_PARSER_MODE="mock",
    )
    client = RecordingMockIntentClient(
        {
            "search_query": "wireless earbuds",
            "has_coupon": True,
            "has_cashback": None,
            "freshness": "fresh",
            "sort": "price_asc",
            "confidence": 0.91,
            "reasoning_summary": "should not be used",
        }
    )
    service = LlmIntentParserService(settings, client, router=ExplodingRouter())  # type: ignore[arg-type]

    result = service.parse("Find fresh wireless earbuds with coupon")

    assert result.fallback_required is True
    assert result.fallback_reason == "router selected intent-parser-v0"
    assert result.model == "intent-parser-v0"
    assert client.last_request is None


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
        assert payload == {
            "active": False,
            "mode": "disabled",
            "default_model": "intent-parser-v0",
            "live_ready": False,
            "available_models": ["intent-parser-v0"],
        }
        assert "openai_api_key" not in response.text.lower()
        assert "dev-admin-token" not in response.text
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
        assert payload["available_models"] == ["intent-parser-v0"]
    finally:
        app.dependency_overrides.clear()
        session.close()
