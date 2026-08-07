from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.rate_limit import (
    MemoryRateLimitStore,
    RateLimitConfig,
    RateLimiter,
    reset_rate_limiter_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_limiters() -> Generator[None, None, None]:
    reset_rate_limiter_for_tests()
    get_settings.cache_clear()
    yield
    reset_rate_limiter_for_tests()
    get_settings.cache_clear()


def test_memory_rate_limiter_blocks_after_limit() -> None:
    limiter = RateLimiter(
        RateLimitConfig(
            enabled=True,
            public_per_minute=2,
            auth_per_minute=10,
            admin_per_minute=10,
        ),
        MemoryRateLimitStore(),
        store_name="memory",
    )
    assert limiter.check("public", "ip:1").allowed is True
    assert limiter.check("public", "ip:1").allowed is True
    blocked = limiter.check("public", "ip:1")
    assert blocked.allowed is False
    assert blocked.remaining == 0


def test_rate_limit_middleware_and_admin_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PUBLIC_PER_MINUTE", "2")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "1000")
    monkeypatch.setenv("RATE_LIMIT_ADMIN_PER_MINUTE", "50")
    monkeypatch.setenv("ADMIN_API_TOKEN", "dev-admin-token")
    monkeypatch.setattr(
        "app.services.rate_limit.create_redis_client",
        lambda _url: None,
    )
    get_settings.cache_clear()
    reset_rate_limiter_for_tests()

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
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/bandit/status").status_code == 200
    assert client.get("/bandit/status").status_code == 200
    limited = client.get("/bandit/status")
    assert limited.status_code == 429
    assert limited.json()["bucket"] == "public"

    status = client.get(
        "/admin/rate-limit/status",
        headers={"X-Admin-Token": "dev-admin-token"},
    )
    # Admin bucket still has capacity; may be 429 if admin shared IP burned public only.
    # Admin uses separate bucket — should succeed unless we hammered admin.
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["public_per_minute"] == 2
    assert body["store"] == "memory"
    assert Settings().rate_limit_enabled is True
