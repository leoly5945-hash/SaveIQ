from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.rate_limit import reset_rate_limiter_for_tests


def _client() -> TestClient:
    reset_rate_limiter_for_tests()
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


def test_metrics_endpoint_exposes_http_counters() -> None:
    client = _client()
    assert client.get("/health").status_code == 200
    assert client.get("/bandit/status").status_code == 200
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


def test_metrics_token_required_when_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("METRICS_TOKEN", "metrics-secret")
    get_settings.cache_clear()
    reset_rate_limiter_for_tests()
    client = _client()
    assert client.get("/metrics").status_code == 401
    ok = client.get("/metrics", headers={"X-Metrics-Token": "metrics-secret"})
    assert ok.status_code == 200
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    get_settings.cache_clear()


def test_request_sets_request_id_header() -> None:
    client = _client()
    response = client.get("/bandit/status")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
