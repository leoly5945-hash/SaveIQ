"""Tests for the public ``/acquire`` endpoint (Layer 2 for a real product)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.providers import registry as registry_module
from app.providers.base import ProviderCapability, ProviderPrice, ProviderProduct
from app.providers.registry import ProviderRegistry
from app.services import endpoint_limit

NOW = datetime(2026, 9, 9, tzinfo=UTC)


class FakeKeepa:
    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset({ProviderCapability.get_product, ProviderCapability.get_price})

    def __init__(self, *, category: str, brand: str, title: str, price_cents: int) -> None:
        self._category = category
        self._brand = brand
        self._title = title
        self._price_cents = price_cents

    def is_configured(self) -> bool:
        return True

    async def get_product(self, pid: str) -> ProviderProduct:
        return ProviderProduct(
            provider="keepa",
            provider_product_id=pid,
            title=self._title,
            brand=self._brand,
            category=self._category,
            market="CA",
            currency="CAD",
        )

    async def get_price(self, pid: str) -> ProviderPrice:
        return ProviderPrice(
            provider="keepa",
            provider_product_id=pid,
            price_cents=self._price_cents,
            currency="CAD",
            observed_at=NOW,
            source="keepa:buy_box",
        )


def _client(monkeypatch, adapter: object) -> TestClient:
    reg = ProviderRegistry()
    reg.register(adapter)
    monkeypatch.setattr(registry_module, "_default_registry", reg)
    endpoint_limit.reset_for_tests()
    return TestClient(app)


def test_phone_gets_the_full_option_set(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        FakeKeepa(
            category="Cell Phones",
            brand="Apple",
            title="Apple iPhone 17 Pro 256GB",
            price_cents=159900,
        ),
    )
    r = client.get(
        "/acquire",
        params={"product_id": "B0PHONE0001", "horizon_months": 36, "is_business": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "smartphone"
    kinds = {t["kind"] for t in body["recommendation"]["ranked"]}
    assert {"retail", "financing", "lease", "refurb"} <= kinds
    assert body["recommendation"]["verify_first"]


def test_unrecognised_category_degrades_to_outright_and_renewed(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        FakeKeepa(
            category="Garden Hand Tools",
            brand="Fiskars",
            title="Fiskars Bypass Pruner",
            price_cents=3200,
        ),
    )
    r = client.get("/acquire", params={"product_id": "B0TOOL00001"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "general"
    kinds = {t["kind"] for t in body["recommendation"]["ranked"]}
    assert kinds <= {"retail", "refurb"}
    assert "financing" not in kinds


def test_no_price_is_404(monkeypatch) -> None:
    class NoPrice(FakeKeepa):
        async def get_price(self, pid: str):  # type: ignore[override]
            return None

    client = _client(
        monkeypatch,
        NoPrice(category="Laptop Computers", brand="Dell", title="Dell XPS", price_cents=0),
    )
    assert client.get("/acquire", params={"product_id": "B0LAPTOP001"}).status_code == 404


def test_needs_product_id_or_url(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        FakeKeepa(category="x", brand="y", title="z", price_cents=1000),
    )
    assert client.get("/acquire").status_code == 422


def test_unauthenticated(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        FakeKeepa(category="Cell Phones", brand="Apple", title="iPhone", price_cents=100000),
    )
    # no admin header required
    assert client.get("/acquire", params={"product_id": "B0PHONE0001"}).status_code == 200
