"""'Buy this instead' — find a similar product that's a good buy now."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
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
from app.providers.registry import ProviderRegistry
from app.services import endpoint_limit
from app.services.discovery.alternatives import find_alternatives

NOW = datetime(2026, 9, 10, tzinfo=UTC)


def _history(asin: str, *, flat_at: int | None = None, drops_to: int | None = None):
    if flat_at is not None:  # flat -> FAIR-ish
        pts = [
            ProviderPricePoint(
                observed_at=NOW - timedelta(days=d), price_cents=flat_at, kind="buy_box"
            )
            for d in range(90)
        ]
    else:  # was much higher, now low -> BUY
        pts = [
            ProviderPricePoint(
                observed_at=NOW - timedelta(days=d),
                price_cents=drops_to + (0 if d < 5 else 6000),
                kind="buy_box",
            )
            for d in range(90)
        ]
    return ProviderPriceHistory(
        provider="keepa",
        provider_product_id=asin,
        currency="CAD",
        points=pts,
        metadata={"base_kind": "buy_box"},
    )


class FakeKeepa:
    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset(
        {
            ProviderCapability.search,
            ProviderCapability.get_price,
            ProviderCapability.get_product,
            ProviderCapability.price_history,
        }
    )
    # asin -> (current_cents, history spec)
    CATALOGUE = {
        "B0REF00001": (13000, {"flat_at": 12800}),  # the WAIT product
        "B0ALT00001": (9000, {"drops_to": 9000}),  # cheaper + BUY
        "B0ALT00002": (11000, {"drops_to": 11000}),  # cheaper + BUY
        "B0ALT00003": (15000, {"flat_at": 15000}),  # pricier -> filtered out
        "B0ALT00004": (12000, {"flat_at": 12000}),  # cheaper but FAIR (flat)
    }

    def is_configured(self) -> bool:
        return True

    async def search_products(self, query: str, *, limit: int = 10):
        return [
            ProviderProduct(
                provider="keepa",
                provider_product_id=asin,
                title=f"{query} {asin}",
                brand="Acme",
                category=query,
                market="CA",
                currency="CAD",
            )
            for asin in self.CATALOGUE
        ][:limit]

    async def get_product(self, asin: str):
        return ProviderProduct(
            provider="keepa",
            provider_product_id=asin,
            title="Anker Power Bank",
            brand="Anker",
            category="Portable Power Banks",
            market="CA",
            currency="CAD",
        )

    async def get_price(self, asin: str):
        entry = self.CATALOGUE.get(asin)
        if entry is None:
            return None
        return ProviderPrice(
            provider="keepa",
            provider_product_id=asin,
            price_cents=entry[0],
            currency="CAD",
            observed_at=NOW,
            source="keepa:buy_box",
        )

    async def get_price_history(self, asin: str, *, days: int = 180):
        entry = self.CATALOGUE.get(asin)
        return _history(asin, **entry[1]) if entry else None


def _reg() -> ProviderRegistry:
    r = ProviderRegistry()
    r.register(FakeKeepa())
    return r


@pytest.mark.asyncio
async def test_returns_cheaper_good_buy_candidates_only() -> None:
    res = await find_alternatives(
        _reg(),
        reference_product_id="B0REF00001",
        reference_price_cents=13000,
        title="Anker Power Bank",
        category="Portable Power Banks",
        brand="Anker",
        limit=3,
    )
    ids = [a.product_id for a in res.alternatives]
    assert "B0REF00001" not in ids  # never the product itself
    assert "B0ALT00003" not in ids  # pricier than the reference
    assert set(ids) <= {"B0ALT00001", "B0ALT00002", "B0ALT00004"}
    assert all(a.price_cents <= 13000 for a in res.alternatives)
    assert all(a.verdict in ("BUY", "FAIR") for a in res.alternatives)
    # BUY ranks ahead of FAIR
    verdicts = [a.verdict for a in res.alternatives]
    assert verdicts == sorted(verdicts, key=lambda v: v != "BUY")


@pytest.mark.asyncio
async def test_empty_without_a_search_provider() -> None:
    res = await find_alternatives(
        ProviderRegistry(),
        reference_product_id="B0X",
        reference_price_cents=1000,
        title="x",
        category="x",
        brand=None,
    )
    assert res.alternatives == []


def test_endpoint_returns_alternatives(monkeypatch) -> None:
    reg = _reg()
    monkeypatch.setattr(registry_module, "_default_registry", reg)
    endpoint_limit.reset_for_tests()
    client = TestClient(app)
    r = client.get("/alternatives", params={"product_id": "B0REF00001"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reference_product_id"] == "B0REF00001"
    assert body["reference_price_cents"] == 13000
    assert len(body["alternatives"]) >= 1
    assert all(a["price_cents"] <= 13000 for a in body["alternatives"])


def test_endpoint_needs_input(monkeypatch) -> None:
    monkeypatch.setattr(registry_module, "_default_registry", _reg())
    endpoint_limit.reset_for_tests()
    assert TestClient(app).get("/alternatives").status_code == 422
