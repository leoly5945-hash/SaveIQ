"""Unit tests for :class:`app.providers.dataforseo.DataForSEOProvider`.

Synthetic DataForSEO responses — no network call.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from typing import Any

import pytest

from app.providers.base import ProviderCapability, ProviderError
from app.providers.dataforseo import (
    DataForSEOProvider,
    UrllibDataForSEOTransport,
    _as_price_cents,
)


def _response(
    items: list[dict[str, Any]], *, status: int = 20000, task_status: int = 20000
) -> dict:
    return {
        "status_code": status,
        "status_message": "Ok." if status == 20000 else "Error.",
        "cost": 0.004,
        "tasks": [
            {
                "status_code": task_status,
                "status_message": "Ok." if task_status == 20000 else "Task error.",
                "result": [{"keyword": "anker solix s2000", "items": items}],
            }
        ],
    }


_ITEMS = [
    {
        "type": "google_shopping_serp",
        "title": "Anker SOLIX S2000 Portable Power Station",
        "seller": "Best Buy Canada",
        "price": 949.99,
        "currency": "CAD",
        "product_id": "111",
        "url": "https://www.bestbuy.ca/en-ca/product/anker-solix-s2000",
        "rating": {"value": 4.6},
    },
    {
        "title": "Anker SOLIX S2000 Power Station 2010Wh",
        "seller": "Walmart Canada",
        "price": 899.0,
        "currency": "CAD",
        "product_id": "222",
        "url": "https://www.walmart.ca/en/ip/anker-solix-s2000/123",
        "price_shipping": 0,
    },
    {
        "title": "Junk with no price",
        "seller": "Newegg Canada",
    },
    {
        "title": "No seller",
        "price": 500.0,
    },
]


class FakeTransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, str, Sequence[Mapping[str, Any]]]] = []

    def post_json(
        self,
        url: str,
        *,
        auth_header: str,
        payload: Sequence[Mapping[str, Any]],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.calls.append((url, auth_header, payload))
        return self.response


def _provider(response: Mapping[str, Any], *, login: str | None = "u", password: str | None = "p"):
    return DataForSEOProvider(
        login=login,
        password=password,
        location_code=2124,
        transport=FakeTransport(response),
    )


def test_locale_and_capabilities() -> None:
    p = _provider(_response(_ITEMS))
    assert p.name == "dataforseo"
    assert p.market == "CA"
    assert p.currency == "CAD"
    assert ProviderCapability.get_offers in p.capabilities
    assert ProviderCapability.price_history not in p.capabilities


def test_is_configured() -> None:
    assert _provider(_response([]), password=None).is_configured() is False
    assert _provider(_response([])).is_configured() is True


@pytest.mark.asyncio
async def test_not_configured_raises() -> None:
    with pytest.raises(ProviderError):
        await _provider(_response([]), login=None).get_offers("anything")


@pytest.mark.asyncio
async def test_get_offers_maps_sellers_and_skips_bad_rows() -> None:
    offers = await _provider(_response(_ITEMS)).get_offers("anker solix s2000")
    assert [o.merchant for o in offers] == ["Best Buy Canada", "Walmart Canada"]
    bby, wmt = offers
    assert bby.price_cents == 94999
    assert bby.currency == "CAD"
    assert bby.url and "bestbuy.ca" in bby.url
    assert wmt.price_cents == 89900
    assert wmt.provider_product_id == "anker solix s2000"


@pytest.mark.asyncio
async def test_get_price_returns_cheapest() -> None:
    price = await _provider(_response(_ITEMS)).get_price("anker solix s2000")
    assert price is not None
    assert price.price_cents == 89900
    assert price.source == "google_shopping:Walmart Canada"
    assert price.metadata["offer_count"] == 2


@pytest.mark.asyncio
async def test_search_products_and_limit() -> None:
    results = await _provider(_response(_ITEMS)).search_products("anker", limit=1)
    assert len(results) == 1
    assert results[0].title.startswith("Anker SOLIX S2000")
    assert results[0].metadata["seller"] == "Best Buy Canada"
    assert results[0].metadata["price_cents"] == 94999


@pytest.mark.asyncio
async def test_price_history_is_none() -> None:
    assert await _provider(_response(_ITEMS)).get_price_history("x") is None


@pytest.mark.asyncio
async def test_api_error_status_raises() -> None:
    with pytest.raises(ProviderError, match="40501"):
        await _provider(_response([], status=40501)).get_offers("x")


@pytest.mark.asyncio
async def test_task_error_status_raises() -> None:
    with pytest.raises(ProviderError, match="task error"):
        await _provider(_response([], task_status=40102)).get_offers("x")


@pytest.mark.asyncio
async def test_empty_result_is_empty_offers() -> None:
    assert await _provider(_response([])).get_offers("nothing found") == []


def test_as_price_cents() -> None:
    assert _as_price_cents(9.99) == 999
    assert _as_price_cents("12.50") == 1250
    assert _as_price_cents(0) is None
    assert _as_price_cents(None) is None
    assert _as_price_cents("free") is None


def test_transport_basic_auth_and_gzip(monkeypatch) -> None:
    body = gzip.compress(json.dumps(_response([])).encode("utf-8"))
    captured: dict[str, Any] = {}

    class _Resp:
        headers = {"Content-Encoding": "gzip"}

        def read(self) -> bytes:
            return body

    @contextmanager
    def fake_urlopen(request, timeout):
        captured["auth"] = request.headers.get("Authorization")
        captured["data"] = request.data
        yield _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = UrllibDataForSEOTransport().post_json(
        "https://api.dataforseo.com/v3/merchant/google/products/live/advanced",
        auth_header="Basic abc123",
        payload=[{"keyword": "x"}],
        timeout_seconds=5,
    )
    assert out["status_code"] == 20000
    assert captured["auth"] == "Basic abc123"
    assert json.loads(captured["data"]) == [{"keyword": "x"}]
