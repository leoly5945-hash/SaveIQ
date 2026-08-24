"""Gate 10C canary assignment and admin controls."""

from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.canary.context import bind_canary_request, clear_canary_request
from app.services.canary.effective import is_feature_active
from app.services.canary.service import CanaryService, reset_canary_service_for_tests
from app.services.rate_limit import reset_rate_limiter_for_tests
from app.services.router.ai_router import AiRouter
from app.services.router.contract import RouteRequest
from app.services.safety.service import reset_safety_service_for_tests


def test_canary_settings_default_off() -> None:
    settings = Settings()
    assert settings.canary_enabled is False
    assert settings.canary_percentage == 0
    assert settings.canary_sticky_session is True


def test_hash_assignment_is_stable() -> None:
    service = CanaryService(
        Settings(CANARY_ENABLED="true", CANARY_PERCENTAGE="100"),
        redis_client=None,
    )
    service.set_config(enabled=True, percentage=100)
    identity = "user:canary_user_01"
    assert service.is_canary(identity, "router") is True
    assert service.is_canary(identity, "router") is True


def test_percentage_zero_keeps_everyone_in_control() -> None:
    service = CanaryService(
        Settings(CANARY_ENABLED="true", CANARY_PERCENTAGE="0"),
        redis_client=None,
    )
    service.set_config(enabled=True, percentage=0)
    assert service.is_canary("user:anyone", "router") is False
    assert service.cohort_for("user:anyone") == "control"


def test_feature_list_filters_canary() -> None:
    service = CanaryService(Settings(), redis_client=None)
    service.set_config(enabled=True, percentage=100, features=["bandit"])
    assert service.is_canary("user:x", "bandit") is True
    assert service.is_canary("user:x", "router") is False


def test_is_feature_active_respects_global_when_canary_off() -> None:
    reset_canary_service_for_tests()
    off = Settings(FEATURE_AI_ROUTER="false", CANARY_ENABLED="false")
    on = Settings(FEATURE_AI_ROUTER="true", CANARY_ENABLED="false")
    assert is_feature_active("router", settings=off) is False
    assert is_feature_active("router", settings=on) is True
    reset_canary_service_for_tests()


def test_canary_enables_router_for_cohort_without_global_flag() -> None:
    reset_canary_service_for_tests()
    reset_safety_service_for_tests()
    settings = Settings(
        FEATURE_AI_ROUTER="false",
        AI_ROUTER_MODE="disabled",
        CANARY_ENABLED="true",
        CANARY_PERCENTAGE="100",
        CANARY_STICKY_SESSION="false",
    )
    service = CanaryService(settings, redis_client=None)
    service.set_config(enabled=True, percentage=100, sticky_session=False)
    identity = service.identity_for("canary_user_01", None)
    bind_canary_request(identity=identity, cohort="canary")
    try:
        import app.services.canary.service as canary_mod

        canary_mod._service = service
        assert is_feature_active("router", settings=settings) is True
        router = AiRouter(settings)
        # With canary + disabled mode → mock path should run, not hard-disabled.
        assert router._router_active() is True
        result = router.execute(
            RouteRequest(query_text="cheap laptop", intent_type="recommendation", market="CA")
        )
        assert result.fallback_reason != "AI router disabled"
        assert result.decision.selected_provider == "mock"
    finally:
        clear_canary_request()
        reset_canary_service_for_tests()


def test_control_cohort_keeps_router_off() -> None:
    reset_canary_service_for_tests()
    reset_safety_service_for_tests()
    settings = Settings(
        FEATURE_AI_ROUTER="false",
        AI_ROUTER_MODE="disabled",
        CANARY_ENABLED="true",
        CANARY_PERCENTAGE="0",
    )
    service = CanaryService(settings, redis_client=None)
    service.set_config(enabled=True, percentage=0)
    import app.services.canary.service as canary_mod

    canary_mod._service = service
    bind_canary_request(identity="user:control", cohort="control")
    try:
        assert is_feature_active("router", settings=settings) is False
        assert AiRouter(settings)._router_active() is False
    finally:
        clear_canary_request()
        reset_canary_service_for_tests()


def _admin_client() -> TestClient:
    reset_rate_limiter_for_tests()
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


def test_admin_canary_status_and_config() -> None:
    client = _admin_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    status = client.get("/admin/canary/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is False
    assert body["percentage"] == 0
    assert "router" in body["features"]

    updated = client.post(
        "/admin/canary/config",
        headers=headers,
        json={"enabled": True, "percentage": 1, "features": ["router", "bandit"]},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is True
    assert updated.json()["percentage"] == 1
    assert updated.json()["features"] == ["router", "bandit"]

    stats = client.get("/admin/canary/stats", headers=headers)
    assert stats.status_code == 200
    assert "assignments" in stats.json()

    # Rollback
    rolled = client.post(
        "/admin/canary/config",
        headers=headers,
        json={"enabled": False, "percentage": 0},
    )
    assert rolled.status_code == 200
    assert rolled.json()["enabled"] is False
    reset_canary_service_for_tests()


def test_admin_canary_rejects_unknown_feature() -> None:
    client = _admin_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    response = client.post(
        "/admin/canary/config",
        headers=headers,
        json={"features": ["not_a_feature"]},
    )
    assert response.status_code == 400
    reset_canary_service_for_tests()
