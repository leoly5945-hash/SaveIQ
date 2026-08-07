"""Gate 7 contextual bandit unit and admin API tests."""

from __future__ import annotations

import random
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.bandit.agent import ContextualBanditAgent
from app.services.bandit.features import FEATURE_NAMES, BanditContext, build_feature_vector
from app.services.bandit.offline import evaluate_offline
from app.services.bandit.reward import calculate_reward
from app.services.bandit.service import (
    BanditRouterService,
    reset_bandit_singleton,
)
from app.services.router.ai_router import AiRouter
from app.services.router.cache import RouterIntentCache
from app.services.router.contract import RouteRequest
from app.services.router.metrics import InMemoryMetricsStore, RouterMetrics
from app.services.router.providers.mock_provider import MockProvider


@pytest.fixture(autouse=True)
def _reset_bandit() -> Generator[None, None, None]:
    reset_bandit_singleton()
    yield
    reset_bandit_singleton()


def test_feature_vector_has_fixed_dimension() -> None:
    vector = build_feature_vector(BanditContext(query_text="cheap milk under 5 dollars"))
    assert len(vector) == len(FEATURE_NAMES)
    assert vector[0] == 1.0


def test_reward_prefers_high_quality_low_cost_low_latency() -> None:
    good = calculate_reward(
        confidence=0.9,
        estimated_cost_usd=0.001,
        latency_ms=100,
        success=True,
    )
    bad = calculate_reward(
        confidence=0.4,
        estimated_cost_usd=0.04,
        latency_ms=4000,
        success=True,
    )
    failed = calculate_reward(
        confidence=None,
        estimated_cost_usd=None,
        latency_ms=None,
        success=False,
    )
    assert good.reward > bad.reward
    assert failed.reward == 0.0


def test_linucb_learns_preferred_action() -> None:
    agent = ContextualBanditAgent(
        actions=("openai", "anthropic"),
        feature_dim=len(FEATURE_NAMES),
        alpha=0.5,
        epsilon=0.0,
        min_samples_ready=5,
        rng=random.Random(7),
    )
    context = build_feature_vector(BanditContext(query_text="simple milk deal"))
    for _ in range(20):
        agent.update(context, "openai", 0.9)
        agent.update(context, "anthropic", 0.1)
    choice = agent.choose_action(context, force_explore=False)
    assert choice.action == "openai"
    assert agent.ready is True


def test_bandit_logging_mode_does_not_override_rule() -> None:
    from app.services.router.contract import IntentComplexity

    settings = Settings(
        FEATURE_BANDIT_ROUTER="true",
        BANDIT_ROUTER_MODE="logging",
        BANDIT_MIN_SAMPLES_READY="0",
    )
    service = BanditRouterService(settings)
    vector = build_feature_vector(BanditContext(query_text="milk"))
    for _ in range(12):
        service.agent.update(vector, "openai", 0.8)

    decision = service.decide(
        query_text="milk",
        intent_type="recommendation",
        market="CA",
        user_id=None,
        rule_action="mock",
        available_actions=["mock", "openai"],
        complexity=IntentComplexity.SIMPLE,
    )
    assert decision.selected_action == "mock"
    assert decision.applied is False
    assert decision.mode == "logging"


def test_bandit_active_mode_applies_when_ready() -> None:
    from app.services.router.contract import IntentComplexity

    settings = Settings(
        FEATURE_BANDIT_ROUTER="true",
        BANDIT_ROUTER_MODE="active",
        BANDIT_MIN_SAMPLES_READY="5",
        BANDIT_EPSILON="0",
    )
    service = BanditRouterService(settings)
    context = build_feature_vector(BanditContext(query_text="complex organic groceries"))
    for _ in range(10):
        service.agent.update(context, "anthropic", 0.95)
    decision = service.decide(
        query_text="complex organic groceries",
        intent_type="recommendation",
        market="CA",
        user_id="u1",
        rule_action="openai",
        available_actions=["openai", "anthropic"],
        complexity=IntentComplexity.COMPLEX,
    )
    assert decision.applied is True
    assert decision.selected_action == "anthropic"


def test_offline_evaluation_runs() -> None:
    agent = ContextualBanditAgent(
        actions=("openai", "anthropic"),
        feature_dim=len(FEATURE_NAMES),
        epsilon=0.0,
        min_samples_ready=1,
        rng=random.Random(1),
    )
    features = {
        name: value
        for name, value in zip(
            FEATURE_NAMES,
            build_feature_vector(BanditContext(query_text="milk")),
            strict=True,
        )
    }
    logs = [
        {"features": features, "action": "openai", "reward": 0.8, "rule_action": "openai"},
        {"features": features, "action": "anthropic", "reward": 0.2, "rule_action": "openai"},
    ]
    result = evaluate_offline(logs, agent=agent)
    assert result.samples == 2
    assert "openai" in result.action_counts


def test_router_logging_bandit_keeps_mock_provider() -> None:
    from app.services.router.contract import IntentComplexity

    settings = Settings(
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="mock",
        FEATURE_BANDIT_ROUTER="true",
        BANDIT_ROUTER_MODE="logging",
    )
    bandit = BanditRouterService(settings)
    router = AiRouter(
        settings,
        providers={"mock": MockProvider()},
        cache=RouterIntentCache(None, enabled=False, ttl_seconds=60),
        metrics=RouterMetrics(InMemoryMetricsStore()),
        bandit=bandit,
    )
    result = router.execute(
        RouteRequest(query_text="Find cheap milk", market="CA", intent_type="recommendation")
    )
    assert result.fallback_required is False
    assert result.decision.selected_provider == "mock"
    assert result.decision.complexity == IntentComplexity.SIMPLE


def test_admin_and_public_bandit_endpoints() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_settings() -> Settings:
        return Settings(
            FEATURE_BANDIT_ROUTER="false",
            BANDIT_ROUTER_MODE="disabled",
            ADMIN_API_TOKEN="dev-admin-token",
        )

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    from app.core.settings import get_settings

    app.dependency_overrides[get_settings] = override_settings

    client = TestClient(app)
    headers = {"X-Admin-Token": "dev-admin-token"}

    public = client.get("/bandit/status")
    assert public.status_code == 200
    assert public.json()["mode"] == "disabled"
    assert public.json()["controls_routing"] is False

    status = client.get("/admin/bandit/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["feature_enabled"] is False
    assert body["agent"]["algorithm"] == "linucb"
    assert "bias" in body["features"]

    metrics = client.get("/admin/bandit/metrics", headers=headers)
    assert metrics.status_code == 200
    assert "cumulative_reward" in metrics.json()

    train = client.post("/admin/bandit/train", headers=headers, json={"limit": 10})
    assert train.status_code == 200

    reset = client.post("/admin/bandit/reset", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["agent"]["sample_count"] == 0


def test_bandit_settings_default_off() -> None:
    settings = Settings()
    assert settings.feature_bandit_router is False
    assert settings.bandit_router_mode == "disabled"
    assert settings.bandit_epsilon == 0.1
