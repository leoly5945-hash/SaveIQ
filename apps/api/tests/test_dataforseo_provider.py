"""Unit tests for :class:`app.providers.dataforseo.DataForSEOProvider`.

DataForSEO's Google Shopping is task-based: ``task_post`` a keyword, then
``task_get`` the result. Synthetic responses — no network call.
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

_TASK_ID = "00000000-0000-4000-8000-000000000abc"


def _post_response(*, status: int = 20000, task_status: int = 20100) -> dict:
    return {
        "status_code": status,
        "status_message": "Ok." if status == 20000 else "Error.",
        "cost": 0.02,
        "tasks": [
            {
                "status_code": task_status,
                "status_message": "Task Created." if task_status == 20100 else "Task error.",
                "id": _TASK_ID if task_status in (20000, 20100) else None,
            }
        ],
    }


def _get_response(items: list[dict[str, Any]] | None, *, task_status: int = 20000) -> dict:
    task: dict[str, Any] = {
        "status_code": task_status,
        "status_message": "Ok." if task_status == 20000 else "In queue.",
        "id": _TASK_ID,
    }
    if items is not None:
        task["result"] = [{"keyword": "anker solix s2000", "items": items}]
    return {"status_code": 20000, "status_message": "Ok.", "cost": 0, "tasks": [task]}


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
        "delivery_info": {"delivery_price": {"price": 12.0}},
    },
    {"title": "Junk with no price", "seller": "Newegg Canada"},
    {"title": "No seller", "price": 500.0},
]


class FakeTransport:
    """Answers task_post once, then task_get from a queue of responses."""

    def __init__(
        self,
        *,
        post: Mapping[str, Any] | None = None,
        gets: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self.post = post or _post_response()
        self.gets = list(gets or [_get_response(_ITEMS)])
        self.post_calls: list[tuple[str, str, Sequence[Mapping[str, Any]]]] = []
        self.get_calls: list[tuple[str, str]] = []

    def post_json(
        self,
        url: str,
        *,
        auth_header: str,
        payload: Sequence[Mapping[str, Any]],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.post_calls.append((url, auth_header, payload))
        return self.post

    def get_json(
        self,
        url: str,
        *,
        auth_header: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.get_calls.append((url, auth_header))
        return self.gets.pop(0) if len(self.gets) > 1 else self.gets[0]


def _provider(
    transport: FakeTransport | None = None,
    *,
    login: str | None = "u",
    password: str | None = "p",
):
    return DataForSEOProvider(
        login=login,
        password=password,
        location_code=2124,
        transport=transport or FakeTransport(),
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _fast(_seconds):
        return None

    monkeypatch.setattr("app.providers.dataforseo.asyncio.sleep", _fast)


def test_locale_and_capabilities() -> None:
    p = _provider()
    assert p.name == "dataforseo"
    assert p.market == "CA"
    assert p.currency == "CAD"
    assert ProviderCapability.get_offers in p.capabilities
    assert ProviderCapability.price_history not in p.capabilities


def test_is_configured() -> None:
    assert _provider(password=None).is_configured() is False
    assert _provider().is_configured() is True


@pytest.mark.asyncio
async def test_not_configured_raises() -> None:
    with pytest.raises(ProviderError):
        await _provider(login=None).submit_offers_task("anything")


@pytest.mark.asyncio
async def test_submit_offers_task_posts_and_returns_id() -> None:
    transport = FakeTransport()
    p = _provider(transport)
    task_id = await p.submit_offers_task("anker solix s2000")
    assert task_id == _TASK_ID
    url, auth, payload = transport.post_calls[0]
    assert url.endswith("/v3/merchant/google/products/task_post")
    assert auth.startswith("Basic ")
    assert payload[0]["keyword"] == "anker solix s2000"
    assert payload[0]["location_code"] == 2124
    assert payload[0]["priority"] == 2


@pytest.mark.asyncio
async def test_submit_offers_task_error_raises() -> None:
    transport = FakeTransport(post=_post_response(task_status=40102))
    with pytest.raises(ProviderError, match="task_post error"):
        await _provider(transport).submit_offers_task("x")


@pytest.mark.asyncio
async def test_fetch_offers_task_pending_returns_none() -> None:
    transport = FakeTransport(gets=[_get_response(None, task_status=40602)])
    assert await _provider(transport).fetch_offers_task(_TASK_ID) is None


@pytest.mark.asyncio
async def test_fetch_offers_task_ready_maps_and_skips_bad_rows() -> None:
    transport = FakeTransport(gets=[_get_response(_ITEMS)])
    offers = await _provider(transport).fetch_offers_task(_TASK_ID, provider_product_id="ref")
    assert offers is not None
    assert [o.merchant for o in offers] == ["Best Buy Canada", "Walmart Canada"]
    bby, wmt = offers
    assert bby.price_cents == 94999
    assert bby.url and "bestbuy.ca" in bby.url
    assert wmt.price_cents == 89900
    assert wmt.shipping_cents == 1200  # from delivery_info.delivery_price
    assert wmt.total_cents == 91100
    assert wmt.provider_product_id == "ref"
    url, _auth = transport.get_calls[0]
    assert url.endswith(f"/v3/merchant/google/products/task_get/advanced/{_TASK_ID}")


@pytest.mark.asyncio
async def test_fetch_offers_task_hard_error_raises() -> None:
    transport = FakeTransport(gets=[_get_response(None, task_status=40501)])
    with pytest.raises(ProviderError, match="task_get error"):
        await _provider(transport).fetch_offers_task(_TASK_ID)


@pytest.mark.asyncio
async def test_fetch_offers_task_ready_but_empty_is_empty_list() -> None:
    transport = FakeTransport(gets=[_get_response([])])
    assert await _provider(transport).fetch_offers_task(_TASK_ID) == []


@pytest.mark.asyncio
async def test_get_offers_submits_then_polls_until_ready() -> None:
    transport = FakeTransport(
        gets=[
            _get_response(None, task_status=40602),
            _get_response(_ITEMS),
        ]
    )
    offers = await _provider(transport).get_offers("anker solix s2000")
    assert [o.merchant for o in offers] == ["Best Buy Canada", "Walmart Canada"]
    assert len(transport.post_calls) == 1
    assert len(transport.get_calls) >= 2


@pytest.mark.asyncio
async def test_get_price_returns_cheapest() -> None:
    price = await _provider().get_price("anker solix s2000")
    assert price is not None
    assert price.price_cents == 89900
    assert price.source == "google_shopping:Walmart Canada"
    assert price.metadata["offer_count"] == 2


@pytest.mark.asyncio
async def test_search_products_and_limit() -> None:
    results = await _provider().search_products("anker", limit=1)
    assert len(results) == 1
    assert results[0].title.startswith("Anker SOLIX S2000")
    assert results[0].metadata["seller"] == "Best Buy Canada"


@pytest.mark.asyncio
async def test_price_history_is_none() -> None:
    assert await _provider().get_price_history("x") is None


@pytest.mark.asyncio
async def test_api_envelope_error_raises() -> None:
    transport = FakeTransport(post=_post_response(status=40501))
    with pytest.raises(ProviderError, match="40501"):
        await _provider(transport).submit_offers_task("x")


def test_as_price_cents() -> None:
    assert _as_price_cents(9.99) == 999
    assert _as_price_cents("12.50") == 1250
    assert _as_price_cents(0) is None
    assert _as_price_cents(None) is None
    assert _as_price_cents("free") is None


def test_transport_post_basic_auth_and_gzip(monkeypatch) -> None:
    body = gzip.compress(json.dumps(_post_response()).encode("utf-8"))
    captured: dict[str, Any] = {}

    class _Resp:
        headers = {"Content-Encoding": "gzip"}

        def read(self) -> bytes:
            return body

    @contextmanager
    def fake_urlopen(request, timeout):
        captured["auth"] = request.headers.get("Authorization")
        captured["method"] = request.method
        captured["data"] = request.data
        yield _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = UrllibDataForSEOTransport().post_json(
        "https://api.dataforseo.com/v3/merchant/google/products/task_post",
        auth_header="Basic abc123",
        payload=[{"keyword": "x"}],
        timeout_seconds=5,
    )
    assert out["status_code"] == 20000
    assert captured["auth"] == "Basic abc123"
    assert captured["method"] == "POST"
    assert json.loads(captured["data"]) == [{"keyword": "x"}]


def test_transport_get_basic_auth_and_gzip(monkeypatch) -> None:
    body = gzip.compress(json.dumps(_get_response(_ITEMS)).encode("utf-8"))
    captured: dict[str, Any] = {}

    class _Resp:
        headers = {"Content-Encoding": "gzip"}

        def read(self) -> bytes:
            return body

    @contextmanager
    def fake_urlopen(request, timeout):
        captured["auth"] = request.headers.get("Authorization")
        captured["method"] = request.method
        yield _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = UrllibDataForSEOTransport().get_json(
        f"https://api.dataforseo.com/v3/merchant/google/products/task_get/advanced/{_TASK_ID}",
        auth_header="Basic abc123",
        timeout_seconds=5,
    )
    assert out["tasks"][0]["result"][0]["items"]
    assert captured["auth"] == "Basic abc123"
    assert captured["method"] == "GET"
