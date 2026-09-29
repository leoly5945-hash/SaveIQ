"""Barcode (UPC / EAN) -> Amazon.ca ASIN lookup: Keepa adapter + public endpoint."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers import registry as registry_module
from app.providers.base import (
    ProviderCapability,
    ProviderError,
    ProviderProduct,
    ProviderProductNotFound,
)
from app.providers.keepa import KeepaProvider
from app.providers.registry import ProviderRegistry
from app.services import endpoint_limit


class _Transport:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def get_json(self, url: str, *, timeout_seconds: float) -> Mapping[str, Any]:
        self.calls.append(url)
        return self.payload


@pytest.mark.asyncio
async def test_keepa_lookup_by_code_returns_asins_and_skips_stubs() -> None:
    transport = _Transport(
        {
            "tokensLeft": 500,
            "products": [
                {"asin": "B000TEST01", "title": "Energizer MAX AA, 20 count"},
                {"asin": "B000STUB00", "title": None},
                {"asin": "B000TEST02", "title": "Energizer MAX AA, 48 count"},
            ],
        }
    )
    keepa = KeepaProvider(api_key="k", domain=6, transport=transport)

    found = await keepa.lookup_by_code(" 039800011329 ")

    assert [p.provider_product_id for p in found] == ["B000TEST01", "B000TEST02"]
    query = parse_qs(urlsplit(transport.calls[0]).query)
    assert query["code"] == ["039800011329"]
    assert query["history"] == ["0"]
    assert query["domain"] == ["6"]


@pytest.mark.asyncio
async def test_keepa_lookup_by_code_rejects_non_barcodes_without_a_call() -> None:
    transport = _Transport({"products": []})
    keepa = KeepaProvider(api_key="k", domain=6, transport=transport)
    for bad in ("B08LF175VC", "1234567", "123456789012345", "12a4567890"):
        with pytest.raises(ProviderProductNotFound):
            await keepa.lookup_by_code(bad)
    assert transport.calls == []


class _FakeKeepa:
    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset({ProviderCapability.search})

    def __init__(self, found: list[ProviderProduct] | Exception) -> None:
        self._found = found

    def is_configured(self) -> bool:
        return True

    async def lookup_by_code(self, code: str, *, limit: int = 3) -> list[ProviderProduct]:
        if isinstance(self._found, Exception):
            raise self._found
        return self._found


def _client(monkeypatch, keepa: _FakeKeepa) -> TestClient:
    reg = ProviderRegistry()
    reg.register(keepa)
    monkeypatch.setattr(registry_module, "_default_registry", reg)
    endpoint_limit.reset_for_tests()
    return TestClient(app)


def _product(asin: str, title: str) -> ProviderProduct:
    return ProviderProduct(
        provider="keepa", provider_product_id=asin, title=title, market="CA", currency="CAD"
    )


def test_barcode_endpoint_returns_matches(monkeypatch) -> None:
    client = _client(monkeypatch, _FakeKeepa([_product("B000TEST01", "Batteries")]))
    resp = client.get("/check/barcode?code=039800011329")
    assert resp.status_code == 200
    assert resp.json() == {
        "code": "039800011329",
        "matches": [{"asin": "B000TEST01", "title": "Batteries"}],
    }


def test_barcode_endpoint_404_when_not_on_amazon_ca(monkeypatch) -> None:
    client = _client(monkeypatch, _FakeKeepa([]))
    resp = client.get("/check/barcode?code=039800011329")
    assert resp.status_code == 404
    assert "couldn't find that barcode" in resp.json()["detail"]


def test_barcode_endpoint_validates_the_code(monkeypatch) -> None:
    client = _client(monkeypatch, _FakeKeepa([]))
    assert client.get("/check/barcode?code=B08LF175VC").status_code == 422
    assert client.get("/check/barcode?code=123").status_code == 422


def test_barcode_endpoint_maps_provider_errors(monkeypatch) -> None:
    client = _client(monkeypatch, _FakeKeepa(ProviderError("Keepa error: boom")))
    assert client.get("/check/barcode?code=039800011329").status_code == 502
