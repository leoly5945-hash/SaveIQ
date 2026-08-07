"""Gate 10D A/B testing service and admin API."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.abtest.context import bind_abtest_request, clear_abtest_request
from app.services.abtest.service import ABTestService, reset_abtest_service_for_tests
from app.services.canary.effective import effective_ai_router_mode, is_feature_active
from app.services.canary.service import reset_canary_service_for_tests
from app.services.rate_limit import reset_rate_limiter_for_tests
from app.services.router.ai_router import AiRouter
from app.services.router.contract import RouteRequest

FIXTURE_YAML = Path(__file__).resolve().parents[1] / "config" / "abtest.yaml"


def test_abtest_settings_default_off() -> None:
    settings = Settings()
    assert settings.feature_abtest_enabled is False
    assert settings.abtest_redis_ttl == 2592000
    assert settings.abtest_config_path == "config/abtest.yaml"


def test_sticky_assignment_is_stable() -> None:
    settings = Settings(
        FEATURE_ABTEST_ENABLED="true",
        ABTEST_CONFIG_PATH=str(FIXTURE_YAML),
    )
    service = ABTestService(settings, redis_client=None)
    service.start("router_holdout_v1")
    first = service.assign_user("ab_user_stable_01")
    second = service.assign_user("ab_user_stable_01")
    assert first == second
    assert first in {"control", "treatment_a"}


def test_md5_bucket_deterministic() -> None:
    settings = Settings(
        FEATURE_ABTEST_ENABLED="true",
        ABTEST_CONFIG_PATH=str(FIXTURE_YAML),
    )
    service = ABTestService(settings, redis_client=None)
    service.start()
    a = service._bucket("user_x", "router_holdout_v1")
    b = service._bucket("user_x", "router_holdout_v1")
    assert a == b
    assert 0 <= a < 100


def test_get_config_returns_group_overrides() -> None:
    settings = Settings(
        FEATURE_ABTEST_ENABLED="true",
        ABTEST_CONFIG_PATH=str(FIXTURE_YAML),
    )
    service = ABTestService(settings, redis_client=None)
    service.start()
    payload = service.get_config("config_user_01")
    assert payload["group"] in {"control", "treatment_a"}
    assert "feature_ai_router" in payload["config"]


def test_significance_handles_zero_conversions() -> None:
    settings = Settings(
        FEATURE_ABTEST_ENABLED="true",
        ABTEST_CONFIG_PATH=str(FIXTURE_YAML),
    )
    service = ABTestService(settings, redis_client=None)
    service.start()
    for _ in range(10):
        service.log_exposure("c", "control", converted=False)
    for _ in range(12):
        service.log_exposure("t", "treatment_a", converted=False)
    result = service.calculate_significance(metric="conversions")
    assert result["significant"] is False
    assert result.get("error")
    assert result.get("p_value") is None


def test_exposure_and_significance() -> None:
    settings = Settings(
        FEATURE_ABTEST_ENABLED="true",
        ABTEST_CONFIG_PATH=str(FIXTURE_YAML),
    )
    service = ABTestService(settings, redis_client=None)
    service.start()
    # Seed balanced conversion table.
    for _ in range(40):
        service.log_exposure("u1", "control", converted=True)
    for _ in range(60):
        service.log_exposure("u2", "control", converted=False)
    for _ in range(70):
        service.log_exposure("u3", "treatment_a", converted=True)
    for _ in range(30):
        service.log_exposure("u4", "treatment_a", converted=False)

    stats = service.get_stats()
    assert stats["groups"]["control"]["exposures"] == 100
    assert stats["groups"]["treatment_a"]["conversions"] == 70
    result = service.calculate_significance(metric="conversions")
    assert result["p_value"] is not None
    assert "significant" in result


def test_ab_overrides_affect_router_effective_flags() -> None:
    reset_abtest_service_for_tests()
    reset_canary_service_for_tests()
    settings = Settings(
        FEATURE_AI_ROUTER="false",
        AI_ROUTER_MODE="disabled",
        FEATURE_ABTEST_ENABLED="true",
    )
    bind_abtest_request(
        user_id="ab_treat",
        group="treatment_a",
        experiment="router_holdout_v1",
        overrides={"feature_ai_router": True, "ai_router_mode": "mock"},
    )
    try:
        assert is_feature_active("router", settings=settings) is True
        assert effective_ai_router_mode(settings) == "mock"
        router = AiRouter(settings)
        assert router._router_active() is True
        result = router.execute(
            RouteRequest(query_text="laptop deal", intent_type="recommendation", market="CA")
        )
        assert result.fallback_reason != "AI router disabled"
    finally:
        clear_abtest_request()
        reset_abtest_service_for_tests()
        reset_canary_service_for_tests()


def _client() -> TestClient:
    reset_rate_limiter_for_tests()
    reset_abtest_service_for_tests()
    reset_canary_service_for_tests()
    get_settings.cache_clear()
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

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_admin_abtest_lifecycle(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ABTEST_CONFIG_PATH", str(FIXTURE_YAML))
    get_settings.cache_clear()
    client = _client()
    headers = {"X-Admin-Token": "dev-admin-token"}

    status = client.get("/admin/abtest/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["feature_enabled"] is False

    started = client.post(
        "/admin/abtest/start",
        headers=headers,
        json={"experiment": "router_holdout_v1"},
    )
    assert started.status_code == 200
    assert started.json()["running"] is True
    assert started.json()["feature_enabled"] is True

    # Assigned users get X-AB-Group header.
    response = client.get(
        "/health",
        headers={"X-User-ID": "middleware_user_01"},
    )
    assert response.status_code == 200
    assert response.headers.get("x-ab-group") in {"control", "treatment_a", "none"}

    sig = client.get("/admin/abtest/significance", headers=headers)
    assert sig.status_code == 200

    stopped = client.post("/admin/abtest/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["running"] is False
    assert stopped.json()["feature_enabled"] is False

    reset_abtest_service_for_tests()
    get_settings.cache_clear()
