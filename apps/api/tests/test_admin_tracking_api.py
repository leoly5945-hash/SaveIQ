"""Tests for the CP15 admin + public alert endpoints."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.providers import registry as registry_module
from app.providers.base import (
    ProviderCapability,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderProduct,
)
from app.providers.registry import ProviderRegistry

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
HEADERS = {"X-Admin-Token": "dev-admin-token"}


class FakeKeepa:
    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset({ProviderCapability.get_price, ProviderCapability.price_history})

    def __init__(self, price_cents: int = 4300) -> None:
        self.price_cents = price_cents

    def is_configured(self) -> bool:
        return True

    async def get_product(self, pid: str) -> ProviderProduct | None:
        return ProviderProduct(
            provider="keepa",
            provider_product_id=pid,
            title="Anker 737 Power Bank",
            market="CA",
            currency="CAD",
            product_url=f"https://www.amazon.ca/dp/{pid}",
        )

    async def get_price(self, pid: str) -> ProviderPrice | None:
        return ProviderPrice(
            provider="keepa",
            provider_product_id=pid,
            price_cents=self.price_cents,
            currency="CAD",
            observed_at=NOW,
            source="keepa:buy_box",
        )

    async def get_price_history(self, pid: str, *, days: int = 180) -> ProviderPriceHistory | None:
        return ProviderPriceHistory(
            provider="keepa",
            provider_product_id=pid,
            currency="CAD",
            points=[],
            metadata={"keepa_stats": {"avg90_cents": 4600}},
        )


def _client(monkeypatch, provider: object | None) -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

    def override_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_db

    reg = ProviderRegistry()
    if provider is not None:
        reg.register(provider)
    monkeypatch.setattr(registry_module, "_default_registry", reg)
    return TestClient(app), session


def test_create_alert_from_url(monkeypatch) -> None:
    client, session = _client(monkeypatch, FakeKeepa())
    try:
        resp = client.post(
            "/admin/alerts",
            headers=HEADERS,
            json={
                "email": "shopper@example.com",
                "url": "https://www.amazon.ca/Anker-737/dp/B09VPHVT9Z/ref=x",
                "kind": "any_drop",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["email"] == "shopper@example.com"
        assert body["provider_product_id"] == "B09VPHVT9Z"
        assert body["baseline_cents"] == 4300
        assert body["status"] == "active"
        assert "/alerts/unsubscribe?token=" in body["unsubscribe_url"]

        listed = client.get("/admin/alerts", headers=HEADERS)
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_create_alert_rejects_non_ca_url(monkeypatch) -> None:
    client, session = _client(monkeypatch, FakeKeepa())
    try:
        resp = client.post(
            "/admin/alerts",
            headers=HEADERS,
            json={"email": "a@b.co", "url": "https://www.amazon.com/dp/B09VPHVT9Z"},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_run_cycle_fires_alert_after_price_drop(monkeypatch) -> None:
    provider = FakeKeepa(price_cents=5000)
    client, session = _client(monkeypatch, provider)
    try:
        client.post(
            "/admin/alerts",
            headers=HEADERS,
            json={"email": "a@b.co", "product_id": "B09VPHVT9Z", "kind": "any_drop"},
        )
        # Price drops, then run the cycle.
        provider.price_cents = 4200
        run = client.post("/admin/alerts/run", headers=HEADERS)
        assert run.status_code == 200, run.text
        stats = run.json()
        assert stats["alerts_fired"] == 1
        assert stats["emails_sent"] == 1

        assert client.get("/admin/alerts", headers=HEADERS).json()["alerts"][0]["status"] == "fired"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_unsubscribe_is_public_and_idempotent(monkeypatch) -> None:
    client, session = _client(monkeypatch, FakeKeepa())
    try:
        created = client.post(
            "/admin/alerts",
            headers=HEADERS,
            json={"email": "a@b.co", "product_id": "B09VPHVT9Z"},
        ).json()
        token = created["unsubscribe_url"].split("token=")[1]

        r1 = client.get("/alerts/unsubscribe", params={"token": token})  # no admin header
        assert r1.status_code == 200 and r1.json()["ok"] is True
        r2 = client.get("/alerts/unsubscribe", params={"token": token})
        assert r2.status_code == 200

        assert client.get("/admin/alerts", headers=HEADERS).json()["alerts"][0]["status"] == (
            "unsubscribed"
        )
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_admin_alerts_requires_token(monkeypatch) -> None:
    client, session = _client(monkeypatch, FakeKeepa())
    try:
        assert client.get("/admin/alerts").status_code == 401
        assert client.post("/admin/alerts/run").status_code == 401
    finally:
        app.dependency_overrides.clear()
        session.close()
