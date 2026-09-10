"""Public ``/discover`` endpoint."""

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
    capabilities = frozenset({ProviderCapability.search, ProviderCapability.get_price})

    def is_configured(self) -> bool:
        return True

    async def search_products(self, query: str, *, limit: int = 10) -> list[ProviderProduct]:
        return [
            ProviderProduct(
                provider="keepa",
                provider_product_id=f"B0{n}",
                title=f"{query} option {n}",
                market="CA",
                currency="CAD",
            )
            for n in range(1, 4)
        ]

    async def get_price(self, asin: str) -> ProviderPrice:
        cents = {"B01": 7000, "B02": 15000, "B03": 9000}[asin]
        return ProviderPrice(
            provider="keepa",
            provider_product_id=asin,
            price_cents=cents,
            currency="CAD",
            observed_at=NOW,
            source="keepa:buy_box",
        )


def _client(monkeypatch) -> TestClient:
    reg = ProviderRegistry()
    reg.register(FakeKeepa())
    monkeypatch.setattr(registry_module, "_default_registry", reg)
    endpoint_limit.reset_for_tests()
    return TestClient(app)


def test_discover_parses_and_returns_hits(monkeypatch) -> None:
    client = _client(monkeypatch)
    r = client.get("/discover", params={"q": "power bank under $100"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"]["search_terms"] == "power bank"
    assert body["query"]["price_max_cents"] == 10000
    assert body["price_probed"] is True
    ids = [h["product_id"] for h in body["hits"]]
    assert ids[:2] == ["B01", "B03"]  # in budget, cheapest first
    assert body["hits"][-1]["in_budget"] is False


def test_discover_no_budget_still_prices_the_rows(monkeypatch) -> None:
    client = _client(monkeypatch)
    body = client.get("/discover", params={"q": "wireless earbuds"}).json()
    assert body["price_probed"] is True
    assert [h["price_cents"] for h in body["hits"]] == [7000, 9000, 15000]  # cheapest first
    assert all(h["in_budget"] is None for h in body["hits"])


def test_discover_short_query_is_422(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/discover", params={"q": "x"}).status_code == 422


def test_discover_is_unauthenticated(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/discover", params={"q": "laptop stand"}).status_code == 200
