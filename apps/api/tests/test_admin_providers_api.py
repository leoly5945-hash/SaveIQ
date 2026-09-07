"""Tests for the read-only ``/admin/providers`` inspection endpoint (CP4)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.providers import registry as registry_module
from app.providers.keepa import KeepaProvider
from app.providers.registry import ProviderRegistry


class _NullTransport:
    def get_json(self, url: str, *, timeout_seconds: float) -> dict[str, object]:
        raise AssertionError("must not call")  # pragma: no cover


def _install_registry(monkeypatch, *providers) -> None:
    reg = ProviderRegistry()
    for provider in providers:
        reg.register(provider)
    monkeypatch.setattr(registry_module, "_default_registry", reg)


def test_requires_admin_token() -> None:
    client = TestClient(app)
    assert client.get("/admin/providers").status_code == 401


def test_lists_registered_providers(monkeypatch) -> None:
    _install_registry(
        monkeypatch,
        KeepaProvider(api_key="live", domain=6, transport=_NullTransport()),
    )
    client = TestClient(app)
    response = client.get("/admin/providers", headers={"X-Admin-Token": "dev-admin-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    keepa = body["providers"][0]
    assert keepa["name"] == "keepa"
    assert keepa["market"] == "CA"
    assert keepa["currency"] == "CAD"
    assert keepa["configured"] is True
    assert "price_history" in keepa["capabilities"]


def test_reports_empty_when_nothing_registered(monkeypatch) -> None:
    _install_registry(monkeypatch)
    client = TestClient(app)
    response = client.get("/admin/providers", headers={"X-Admin-Token": "dev-admin-token"})
    assert response.status_code == 200
    assert response.json() == {"count": 0, "providers": []}
