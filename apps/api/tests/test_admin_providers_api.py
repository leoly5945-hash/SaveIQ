"""Tests for the ``/admin/providers`` endpoints (CP4 inspect + CP9-11 price-check)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.providers import registry as registry_module
from app.providers.base import (
    ProviderCapability,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderPricePoint,
    ProviderProduct,
)
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


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


class FakeProvider:
    name = "fake"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset(
        {
            ProviderCapability.get_price,
            ProviderCapability.get_product,
            ProviderCapability.price_history,
        }
    )

    def is_configured(self) -> bool:
        return True

    async def search_products(self, query: str, *, limit: int = 10):  # pragma: no cover
        return []

    async def get_product(self, provider_product_id: str) -> ProviderProduct | None:
        return ProviderProduct(
            provider="fake",
            provider_product_id=provider_product_id,
            title="Test Widget",
            market="CA",
            currency="CAD",
            product_url="https://example.test/dp/" + provider_product_id,
        )

    async def get_offers(self, provider_product_id: str):  # pragma: no cover
        return []

    async def get_price(self, provider_product_id: str) -> ProviderPrice | None:
        return ProviderPrice(
            provider="fake",
            provider_product_id=provider_product_id,
            price_cents=4300,
            currency="CAD",
            observed_at=NOW,
            source="fake:buy_box",
        )

    async def get_price_history(
        self, provider_product_id: str, *, days: int = 180
    ) -> ProviderPriceHistory | None:
        points = [
            ProviderPricePoint(
                observed_at=NOW - timedelta(days=d),
                price_cents=5000 - (d % 3) * 40,
                kind="buy_box",
            )
            for d in range(1, 90, 2)
        ]
        return ProviderPriceHistory(
            provider="fake",
            provider_product_id=provider_product_id,
            currency="CAD",
            points=points,
        )


def test_price_check_runs_the_decision_engine(monkeypatch) -> None:
    _install_registry(monkeypatch, FakeProvider())
    client = TestClient(app)
    response = client.get(
        "/admin/providers/price-check",
        params={"product_id": "B0TESTASIN1"},
        headers={"X-Admin-Token": "dev-admin-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert body["title"] == "Test Widget"
    assessment = body["assessment"]
    assert assessment["verdict"] in {"BUY", "FAIR", "WAIT", "UNKNOWN"}
    assert 0 <= assessment["score"] <= 100
    assert assessment["effective_price"]["effective_cents"] == 4300
    assert assessment["intelligence"]["series_kind"] == "buy_box"
    assert assessment["reasons"]


def test_price_check_requires_admin() -> None:
    assert (
        TestClient(app)
        .get("/admin/providers/price-check", params={"product_id": "B0X"})
        .status_code
        == 401
    )


def test_price_check_404_for_unknown_provider(monkeypatch) -> None:
    _install_registry(monkeypatch, FakeProvider())
    client = TestClient(app)
    response = client.get(
        "/admin/providers/price-check",
        params={"product_id": "B0TESTASIN1", "provider": "nope"},
        headers={"X-Admin-Token": "dev-admin-token"},
    )
    assert response.status_code == 404


def test_price_check_accepts_an_amazon_ca_url(monkeypatch) -> None:
    _install_registry(monkeypatch, FakeProvider())
    client = TestClient(app)
    response = client.get(
        "/admin/providers/price-check",
        params={"url": "https://www.amazon.ca/Anker-737/dp/B0TEST0001/ref=x"},
        headers={"X-Admin-Token": "dev-admin-token"},
    )
    assert response.status_code == 200
    assert response.json()["provider_product_id"] == "B0TEST0001"


def test_price_check_rejects_a_non_ca_url(monkeypatch) -> None:
    _install_registry(monkeypatch, FakeProvider())
    client = TestClient(app)
    response = client.get(
        "/admin/providers/price-check",
        params={"url": "https://www.amazon.com/dp/B0TEST0001"},
        headers={"X-Admin-Token": "dev-admin-token"},
    )
    assert response.status_code == 422
    assert "Amazon.ca" in response.json()["detail"]


def test_price_check_needs_id_or_url() -> None:
    client = TestClient(app)
    response = client.get(
        "/admin/providers/price-check", headers={"X-Admin-Token": "dev-admin-token"}
    )
    assert response.status_code == 422
