"""Gate 10E kill switch + auto-tune safety framework."""

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
from app.services.abtest.service import reset_abtest_service_for_tests
from app.services.canary.service import reset_canary_service_for_tests
from app.services.rate_limit import reset_rate_limiter_for_tests
from app.services.router.ai_router import AiRouter, clear_runtime_cache_ttl
from app.services.router.contract import RouteRequest
from app.services.safety.metrics_window import MetricsWindow
from app.services.safety.service import (
    SafetyService,
    TunableHParams,
    build_safety_service,
    kill_switch_forces_router_fallback,
    reset_safety_service_for_tests,
)


def test_safety_settings_default_off() -> None:
    settings = Settings()
    assert settings.feature_kill_switch is False
    assert settings.feature_auto_tuning is False
    assert settings.auto_tune_dry_run is True
    assert settings.auto_tune_canary_enabled is False


def test_metrics_window_error_rate_and_p95() -> None:
    window = MetricsWindow(window_seconds=300)
    for _ in range(90):
        window.record(status_code=200, latency_ms=100.0)
    for _ in range(10):
        window.record(status_code=500, latency_ms=5000.0)
    snap = window.snapshot()
    assert snap.requests == 100
    assert snap.error_rate == 0.1
    assert snap.latency_p95_ms >= 100.0


def test_kill_switch_trips_on_error_rate() -> None:
    reset_safety_service_for_tests()
    reset_canary_service_for_tests()
    reset_abtest_service_for_tests()
    settings = Settings(
        FEATURE_KILL_SWITCH="true",
        FEATURE_AUTO_TUNING="false",
        FEATURE_ABTEST_ENABLED="true",
        KILL_SWITCH_MIN_SAMPLES="20",
        KILL_SWITCH_ERROR_RATE_THRESHOLD="0.05",
        REDIS_URL="",  # force memory backends
    )
    from app.services.abtest.service import build_abtest_service
    from app.services.canary.service import build_canary_service

    canary = build_canary_service(settings)
    canary.set_config(enabled=True, percentage=5)
    ab = build_abtest_service(settings)
    ab.start()

    service = SafetyService(settings, redis_client=None)
    service.set_config(kill_switch_enabled=True, auto_tune_enabled=False, dry_run=True)

    for _ in range(25):
        service.record_request(status_code=500, latency_ms=50.0)
    result = service.evaluate()
    assert result["kill"]["tripped"] is True
    assert "error_rate" in (result["kill"]["reason"] or "")
    assert canary.get_config().percentage == 0
    assert ab.status()["running"] is False
    assert result["kill"].get("router_fallback") is True


def test_manual_override_blocks_trip_and_tune() -> None:
    reset_safety_service_for_tests()
    settings = Settings(
        FEATURE_KILL_SWITCH="true",
        FEATURE_AUTO_TUNING="true",
        KILL_SWITCH_MIN_SAMPLES="5",
    )
    service = SafetyService(settings, redis_client=None)
    service.set_config(
        kill_switch_enabled=True,
        auto_tune_enabled=True,
        manual_override=True,
        dry_run=True,
    )
    for _ in range(20):
        service.record_request(status_code=500, latency_ms=9000.0, cost_usd=1.0)
    result = service.evaluate()
    assert result["kill"]["skipped"] is True
    assert result["tune"]["skipped"] is True


def test_auto_tune_dry_run_proposes_without_apply() -> None:
    reset_safety_service_for_tests()
    clear_runtime_cache_ttl()
    settings = Settings(
        FEATURE_AUTO_TUNING="true",
        FEATURE_KILL_SWITCH="false",
        AUTO_TUNE_DRY_RUN="true",
        AUTO_TUNE_MIN_SAMPLES="10",
        AUTO_TUNE_INTERVAL_SECONDS="0",
        KILL_SWITCH_LATENCY_P95_MS="200",
    )
    service = SafetyService(settings, redis_client=None)
    service.set_config(auto_tune_enabled=True, kill_switch_enabled=False, dry_run=True)
    before = service.get_hparams()
    for _ in range(30):
        service.record_request(status_code=200, latency_ms=180.0)
    result = service.evaluate(force_tune=True)
    assert result["tune"]["dry_run"] is True
    assert result["tune"]["applied"] is False
    after = service.get_hparams()
    assert after.epsilon == before.epsilon


def test_auto_tune_apply_updates_hparams_within_caps() -> None:
    reset_safety_service_for_tests()
    clear_runtime_cache_ttl()
    settings = Settings(
        FEATURE_AUTO_TUNING="true",
        AUTO_TUNE_DRY_RUN="false",
        AUTO_TUNE_EPSILON_MIN="0.05",
        AUTO_TUNE_EPSILON_MAX="0.2",
        AUTO_TUNE_CACHE_TTL_MIN="60",
        AUTO_TUNE_CACHE_TTL_MAX="600",
    )
    service = SafetyService(settings, redis_client=None)
    service.set_config(auto_tune_enabled=True, dry_run=False)
    applied = service.set_hparams(
        TunableHParams(
            epsilon=0.99,
            alpha=0.5,
            beta=0.3,
            gamma=0.2,
            cache_ttl_seconds=9999,
        ),
        reason="test_caps",
    )
    assert applied.epsilon == 0.2
    assert applied.cache_ttl_seconds == 600


def test_autotune_skips_canary_when_abtest_running() -> None:
    reset_safety_service_for_tests()
    reset_abtest_service_for_tests()
    settings = Settings(
        FEATURE_AUTO_TUNING="true",
        FEATURE_ABTEST_ENABLED="true",
        AUTO_TUNE_CANARY_ENABLED="true",
        AUTO_TUNE_DRY_RUN="false",
        AUTO_TUNE_MIN_SAMPLES="5",
        AUTO_TUNE_INTERVAL_SECONDS="0",
        REDIS_URL="",
    )
    from app.services.abtest.service import build_abtest_service

    ab = build_abtest_service(settings)
    ab.start()
    service = SafetyService(settings, redis_client=None)
    service.set_config(
        auto_tune_enabled=True,
        auto_tune_canary_enabled=True,
        dry_run=False,
    )
    for _ in range(20):
        service.record_request(status_code=200, latency_ms=50.0)
    result = service.evaluate(force_tune=True)
    canary = (result.get("tune") or {}).get("canary") or {}
    assert canary.get("skipped") is True
    assert canary.get("reason") == "abtest_running"


def test_admin_safety_endpoints(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reset_safety_service_for_tests()
    reset_rate_limiter_for_tests()
    reset_canary_service_for_tests()
    reset_abtest_service_for_tests()
    clear_runtime_cache_ttl()

    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin")
    monkeypatch.setenv("FEATURE_KILL_SWITCH", "true")
    monkeypatch.setenv("FEATURE_AUTO_TUNING", "true")
    monkeypatch.setenv("FEATURE_AI_ROUTER", "true")
    monkeypatch.setenv("AI_ROUTER_MODE", "mock")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {"X-Admin-Token": "test-admin"}

    status = client.get("/admin/safety/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["env"]["feature_kill_switch"] is True
    assert body["runtime"]["tripped"] is False

    cfg = client.post(
        "/admin/safety/config",
        headers=headers,
        json={"kill_switch_enabled": True, "manual_override": False, "dry_run": True},
    )
    assert cfg.status_code == 200

    trip = client.post(
        "/admin/safety/kill/trip",
        headers=headers,
        json={"reason": "drill", "force": True},
    )
    assert trip.status_code == 200
    assert trip.json()["tripped"] is True

    disarm = client.post("/admin/safety/kill/disarm", headers=headers, json={})
    assert disarm.status_code == 200
    assert disarm.json()["tripped"] is False

    apply = client.post(
        "/admin/safety/autotune/apply",
        headers=headers,
        json={"epsilon": 0.15, "reason": "admin_test"},
    )
    assert apply.status_code == 200
    assert apply.json()["hparams"]["epsilon"] == 0.15

    reset = client.post("/admin/safety/autotune/reset", headers=headers)
    assert reset.status_code == 200

    audit = client.get("/admin/safety/audit", headers=headers)
    assert audit.status_code == 200
    assert isinstance(audit.json()["events"], list)

    ks = client.get("/admin/kill-switch/status", headers=headers)
    assert ks.status_code == 200
    assert ks.json()["tripped"] is False
    assert "request_router_active" in ks.json()

    enabled = client.post(
        "/admin/kill-switch/enable",
        headers=headers,
        json={"reason": "gate10i_test", "trip": True, "force": True},
    )
    assert enabled.status_code == 200
    body_en = enabled.json()
    assert body_en["tripped"] is True
    assert body_en["router_fallback"] is True
    assert body_en["request_router_active"] is False

    disabled = client.post(
        "/admin/kill-switch/disable",
        headers=headers,
        json={"clear_window": True, "unarm": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["tripped"] is False
    assert disabled.json()["router_fallback"] is False
    assert disabled.json()["request_router_active"] is True

    missing = client.get("/admin/kill-switch/status")
    assert missing.status_code == 401

    get_settings.cache_clear()
    reset_safety_service_for_tests()


def test_kill_switch_trip_forces_ai_router_fallback() -> None:
    reset_safety_service_for_tests()
    reset_canary_service_for_tests()
    settings = Settings(
        FEATURE_KILL_SWITCH="true",
        FEATURE_AUTO_TUNING="false",
        FEATURE_AI_ROUTER="true",
        AI_ROUTER_MODE="mock",
        REDIS_URL="",
    )
    service = build_safety_service(settings)
    service.set_config(kill_switch_enabled=True, auto_tune_enabled=False, dry_run=True)
    router = AiRouter(settings)
    request = RouteRequest(query_text="cheap laptop", intent_type="recommendation", market="CA")
    assert router._router_active() is True
    assert kill_switch_forces_router_fallback(settings) is False
    live = router.execute(request)
    assert live.fallback_reason != "AI router disabled"

    trip = service.trip("gate10i_unit", force=True)
    assert trip["tripped"] is True
    assert trip["router_fallback"] is True
    assert kill_switch_forces_router_fallback(settings) is True
    assert router._router_active() is False
    fallback = router.execute(request)
    assert fallback.fallback_required is True
    assert fallback.fallback_reason == "AI router disabled"
    assert fallback.decision.selected_provider == "none"

    service.disarm(clear_window=True)
    assert kill_switch_forces_router_fallback(settings) is False
    assert router._router_active() is True
    reset_safety_service_for_tests()
    reset_canary_service_for_tests()
