"""Unit tests for :class:`app.providers.keepa.KeepaProvider`.

All Keepa responses here are synthetic dev fixtures built in-process — no network
call is made. Timestamps are derived from a pinned ``NOW`` so the trailing-window
filter is deterministic.
"""

from __future__ import annotations

import gzip
import json as _json
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from app.providers.base import ProviderCapability, ProviderError
from app.providers.keepa import (
    _KEEPA_EPOCH_OFFSET_MINUTES,
    KeepaProvider,
    UrllibKeepaHttpTransport,
)

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _keepa_minutes(dt: datetime) -> int:
    return int(dt.timestamp() // 60) - _KEEPA_EPOCH_OFFSET_MINUTES


def _ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


class FakeTransport:
    def __init__(self, *responses: Mapping[str, Any]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def get_json(self, url: str, *, timeout_seconds: float) -> Mapping[str, Any]:
        self.calls.append(url)
        if len(self._responses) == 1:
            return self._responses[0]
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]


def _product(*, with_offers: bool = True, with_stats: bool = True) -> dict[str, Any]:
    csv: list[Any] = [None] * 19
    csv[0] = [  # AMAZON
        _keepa_minutes(_ago(60)),
        4999,
        _keepa_minutes(_ago(20)),
        4599,
        _keepa_minutes(_ago(2)),
        4299,
    ]
    csv[1] = [  # NEW
        _keepa_minutes(_ago(60)),
        4899,
        _keepa_minutes(_ago(2)),
        4199,
    ]
    csv[2] = [_keepa_minutes(_ago(45)), 3999]  # USED (outside a 30d window)
    csv[4] = [_keepa_minutes(_ago(60)), 5999]  # LIST_PRICE
    csv[18] = [  # BUY_BOX_SHIPPING triplets [time, price, shipping]
        _keepa_minutes(_ago(10)),
        4399,
        0,
        _keepa_minutes(_ago(1)),
        4299,
        0,
    ]

    product: dict[str, Any] = {
        "asin": "B09VPHVT9Z",
        "title": "Anker 737 Power Bank (PowerCore 24K)",
        "brand": "Anker",
        "manufacturer": "Anker",
        "productGroup": "Electronics",
        "categoryTree": [
            {"catId": 667823011, "name": "Electronics"},
            {"catId": 7073050011, "name": "Portable Power Banks"},
        ],
        "imagesCSV": "71abcDEF.jpg,71ghiJKL.jpg",
        "upcList": ["842102112345"],
        "csv": csv,
    }
    if with_stats:
        current: list[int] = [-1] * 19
        current[0] = 4299
        current[1] = 4199
        current[4] = 5999
        current[18] = 4299
        avg30: list[int] = [-1] * 19
        avg30[0] = 4400
        avg90: list[int] = [-1] * 19
        avg90[0] = 4650
        stat_min: list[Any] = [None] * 19
        stat_min[0] = [_keepa_minutes(_ago(2)), 4299]
        stat_max: list[Any] = [None] * 19
        stat_max[0] = [_keepa_minutes(_ago(60)), 4999]
        product["stats"] = {
            "current": current,
            "avg30": avg30,
            "avg90": avg90,
            "min": stat_min,
            "max": stat_max,
            "buyBoxSellerId": "ATVPDKIKX0DER",
        }
    if with_offers:
        product["offers"] = [
            {
                "sellerId": "ATVPDKIKX0DER",
                "isAmazon": True,
                "isFBA": True,
                "isPrime": True,
                "condition": 1,
                "offerCSV": [_keepa_minutes(_ago(2)), 4299, 0],
            },
            {
                "sellerId": "A1THIRDPARTY",
                "isAmazon": False,
                "isFBA": True,
                "isPrime": True,
                "condition": 1,
                "offerCSV": [_keepa_minutes(_ago(3)), 4450, 599],
            },
            {
                "sellerId": "A2USEDSELLER",
                "isAmazon": False,
                "isFBA": False,
                "isPrime": False,
                "condition": 3,
                "offerCSV": [_keepa_minutes(_ago(5)), 3800, 0],
            },
        ]
    return product


def _envelope(product: Mapping[str, Any]) -> dict[str, Any]:
    return {"tokensLeft": 1200, "tokensConsumed": 7, "products": [product]}


def _provider(*responses: Mapping[str, Any], api_key: str | None = "test-key") -> KeepaProvider:
    return KeepaProvider(
        api_key=api_key,
        domain=6,
        transport=FakeTransport(*responses),
        now=NOW,
    )


def test_locale_and_capabilities() -> None:
    provider = _provider(_envelope(_product()))
    assert provider.name == "keepa"
    assert provider.market == "CA"
    assert provider.currency == "CAD"
    assert ProviderCapability.price_history in provider.capabilities
    assert ProviderCapability.search in provider.capabilities


def test_is_configured() -> None:
    assert _provider(_envelope(_product())).is_configured() is True
    assert _provider(_envelope(_product()), api_key=None).is_configured() is False


@pytest.mark.asyncio
async def test_not_configured_raises() -> None:
    provider = _provider(_envelope(_product()), api_key=None)
    with pytest.raises(ProviderError):
        await provider.get_price("B09VPHVT9Z")


@pytest.mark.asyncio
async def test_get_product_parses_identity() -> None:
    provider = _provider(_envelope(_product(with_offers=False, with_stats=False)))
    product = await provider.get_product("b09vphvt9z")
    assert product is not None
    assert product.provider_product_id == "B09VPHVT9Z"
    assert product.title.startswith("Anker 737")
    assert product.brand == "Anker"
    assert product.category == "Portable Power Banks"
    assert product.product_url == "https://www.amazon.ca/dp/B09VPHVT9Z"
    assert product.identifiers["asin"] == "B09VPHVT9Z"
    assert product.identifiers["upc"] == "842102112345"
    assert product.image_url is not None and product.image_url.endswith("71abcDEF.jpg")
    assert product.market == "CA"


@pytest.mark.asyncio
async def test_get_product_unknown_asin_returns_none() -> None:
    provider = _provider({"tokensLeft": 10, "products": [{"asin": "B0MISSING", "title": None}]})
    assert await provider.get_product("B0MISSING") is None


@pytest.mark.asyncio
async def test_get_price_prefers_buy_box() -> None:
    provider = _provider(_envelope(_product()))
    price = await provider.get_price("B09VPHVT9Z")
    assert price is not None
    assert price.price_cents == 4299
    assert price.source == "keepa:buy_box"
    assert price.list_price_cents == 5999
    assert price.currency == "CAD"
    assert price.observed_at == NOW


@pytest.mark.asyncio
async def test_get_price_falls_back_to_amazon_without_buy_box() -> None:
    product = _product()
    product["stats"]["current"][18] = -1
    product["csv"][18] = []
    provider = _provider(_envelope(product))
    price = await provider.get_price("B09VPHVT9Z")
    assert price is not None
    assert price.source == "keepa:amazon"
    assert price.price_cents == 4299


@pytest.mark.asyncio
async def test_get_offers_maps_live_offers() -> None:
    provider = _provider(_envelope(_product()))
    offers = await provider.get_offers("B09VPHVT9Z")
    assert len(offers) == 3

    amazon_offer = next(o for o in offers if o.metadata["is_amazon"])
    assert amazon_offer.merchant == "amazon.ca"
    assert amazon_offer.is_buy_box is True
    assert amazon_offer.price_cents == 4299
    assert amazon_offer.condition == "new"

    third_party = next(o for o in offers if o.metadata["seller_id"] == "A1THIRDPARTY")
    assert "3rd party" in third_party.merchant
    assert third_party.price_cents == 4450
    assert third_party.shipping_cents == 599
    assert third_party.total_cents == 5049
    assert third_party.is_buy_box is False

    used = next(o for o in offers if o.metadata["seller_id"] == "A2USEDSELLER")
    assert used.condition == "used"


@pytest.mark.asyncio
async def test_get_offers_synthesises_when_absent() -> None:
    provider = _provider(_envelope(_product(with_offers=False)))
    offers = await provider.get_offers("B09VPHVT9Z")
    assert len(offers) == 1
    assert offers[0].price_cents == 4299
    assert offers[0].metadata["synthesised_from"] == "keepa:buy_box"


@pytest.mark.asyncio
async def test_get_price_history_densifies_the_deepest_series() -> None:
    provider = _provider(_envelope(_product()))
    history = await provider.get_price_history("B09VPHVT9Z", days=90)
    assert history is not None
    assert history.currency == "CAD"

    # AMAZON has the most change points (3) -> it is the base series, forward-filled
    # to one point per day. Every value is one of the three real change values.
    assert history.metadata["base_kind"] == "amazon"
    assert {p.kind for p in history.points} == {"amazon"}
    assert len(history.points) > 60  # ~daily from the first change (~88 days ago)
    assert {p.price_cents for p in history.points} <= {4999, 4599, 4299}
    assert history.points[-1].price_cents == 4299  # latest change carried to now
    assert history.points == sorted(history.points, key=lambda p: p.observed_at)

    assert history.metadata["lifetime_observations"] == 3
    assert history.metadata["source_observations"] == 3  # all 3 changes are within 90d
    ks = history.metadata["keepa_stats"]
    assert ks["min_cents"] == 4299
    assert ks["max_cents"] == 4999
    assert ks["avg90_cents"] == 4650


@pytest.mark.asyncio
async def test_price_history_window_counts_only_recent_changes() -> None:
    provider = _provider(_envelope(_product()))
    history = await provider.get_price_history("B09VPHVT9Z", days=15)
    assert history is not None
    # In a 15-day window only the -2d AMAZON change counts as a real observation,
    # but the series is still forward-filled across the whole window.
    assert history.metadata["source_observations"] == 1
    assert history.metadata["lifetime_observations"] == 3
    assert len(history.points) >= 14


def test_decode_series_skips_malformed_slots() -> None:
    from app.providers.keepa import _decode_series

    row = [100, None, 200, 4400, "x", 4300, 300, 4200]
    out = _decode_series(row, triplet=False)
    assert [price for _, price in out] == [4400, 4200]


def test_densify_daily_forward_fills() -> None:
    from app.providers.keepa import _densify_daily

    start, end = _ago(10), NOW
    cps = [(_ago(8), 1000), (_ago(3), 900)]
    out = _densify_daily(cps, start=start, end=end)
    prices = [price for _, price in out]
    assert prices[0] == 1000  # carried from the first change
    assert prices[-1] == 900  # latest change carried to `end`
    assert set(prices) == {1000, 900}
    assert out[0][0] >= _ago(8)  # nothing emitted before the first observation


@pytest.mark.asyncio
async def test_get_price_survives_null_stats_entries() -> None:
    product = _product(with_offers=False)
    product["stats"]["current"] = [None] * 19  # all unknown
    product["csv"][18] = []
    product["csv"][0] = [_keepa_minutes(_ago(3)), 4250]
    provider = _provider(_envelope(product))
    price = await provider.get_price("B09VPHVT9Z")
    assert price is not None
    assert price.source == "keepa:amazon"
    assert price.price_cents == 4250


@pytest.mark.asyncio
async def test_request_raises_on_keepa_error_object() -> None:
    provider = _provider({"error": {"message": "Invalid api key"}, "tokensLeft": -1})
    with pytest.raises(ProviderError, match="Invalid api key"):
        await provider.get_price("B09VPHVT9Z")


@pytest.mark.asyncio
async def test_search_products_parses_products() -> None:
    p1 = _product(with_offers=False, with_stats=False)
    p2 = dict(p1, asin="B0SECOND", title="Anker Nano Power Bank")
    provider = _provider({"tokensLeft": 900, "products": [p1, p2]})
    results = await provider.search_products("anker power bank", limit=5)
    assert [r.provider_product_id for r in results] == ["B09VPHVT9Z", "B0SECOND"]
    assert all(r.provider == "keepa" for r in results)


@pytest.mark.asyncio
async def test_search_products_returns_empty_for_asinlist_only() -> None:
    provider = _provider({"tokensLeft": 900, "asinList": ["B09VPHVT9Z"]})
    assert await provider.search_products("anything") == []


@pytest.mark.asyncio
async def test_search_products_respects_limit() -> None:
    base = _product(with_offers=False, with_stats=False)
    many = [dict(base, asin=f"B0LIMIT{i}") for i in range(5)]
    provider = _provider({"tokensLeft": 900, "products": many})
    results = await provider.search_products("x", limit=2)
    assert len(results) == 2


class _FakeHTTPResponse:
    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        self._body = body
        self.headers = headers

    def read(self) -> bytes:
        return self._body


def test_urllib_transport_gunzips_response(monkeypatch) -> None:
    # Keepa always gzip-compresses its API responses.
    payload = {"tokensLeft": 42, "products": []}
    gzipped = gzip.compress(_json.dumps(payload).encode("utf-8"))

    @contextmanager
    def fake_urlopen(request, timeout):  # noqa: ARG001
        yield _FakeHTTPResponse(gzipped, {"Content-Encoding": "gzip"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = UrllibKeepaHttpTransport().get_json("https://api.keepa.com/product", timeout_seconds=5)
    assert result == payload


def test_urllib_transport_gunzips_without_header(monkeypatch) -> None:
    # Some proxies drop the Content-Encoding header — sniff the magic bytes.
    payload = {"tokensLeft": 1, "products": []}
    gzipped = gzip.compress(_json.dumps(payload).encode("utf-8"))

    @contextmanager
    def fake_urlopen(request, timeout):  # noqa: ARG001
        yield _FakeHTTPResponse(gzipped, {})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = UrllibKeepaHttpTransport().get_json("https://api.keepa.com/product", timeout_seconds=5)
    assert result == payload


@pytest.mark.asyncio
async def test_prefetch_batches_asins_and_serves_later_calls_from_cache() -> None:
    first = _product(with_offers=False)
    second = {**_product(with_offers=False), "asin": "B0SECOND01", "title": "Second product"}
    stub = {"asin": "B0MISSING", "title": None}
    transport = FakeTransport(
        {"tokensLeft": 900, "tokensConsumed": 6, "products": [first, second, stub]}
    )
    provider = KeepaProvider(api_key="test-key", domain=6, transport=transport, now=NOW)

    cached = await provider.prefetch_products(["b09vphvt9z", "B0SECOND01", "B0MISSING", ""])

    assert cached == 2, "the unknown-ASIN stub is not cached"
    assert len(transport.calls) == 1
    query = parse_qs(urlsplit(transport.calls[0]).query)
    assert query["asin"] == ["B09VPHVT9Z,B0MISSING,B0SECOND01"]
    assert query["stats"] == ["90"]

    price = await provider.get_price("B0SECOND01")
    history = await provider.get_price_history("B09VPHVT9Z", days=90)
    assert price is not None and history is not None
    assert len(transport.calls) == 1, "cached products need no further Keepa call"


@pytest.mark.asyncio
async def test_prefetch_splits_into_batches_of_100() -> None:
    transport = FakeTransport({"tokensLeft": 900, "products": []})
    provider = KeepaProvider(api_key="test-key", domain=6, transport=transport, now=NOW)

    await provider.prefetch_products([f"B0{n:08d}" for n in range(150)])

    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_get_price_is_none_when_keepa_reports_no_current_offer() -> None:
    # Out of stock everywhere: stats.current is -1 for every price type, but the
    # csv still holds older prices. Those must not be passed off as today's.
    product = _product(with_offers=False)
    product["stats"]["current"] = [-1] * 19
    provider = _provider(_envelope(product))
    assert await provider.get_price("B09VPHVT9Z") is None


@pytest.mark.asyncio
async def test_csv_fallback_ignores_a_series_that_ends_with_no_offer() -> None:
    product = _product(with_offers=False, with_stats=False)
    for index in (0, 1, 18):
        row = product["csv"][index]
        step = 3 if index == 18 else 2
        product["csv"][index] = row + [_keepa_minutes(_ago(0.5)), -1] + ([0] if step == 3 else [])
    provider = _provider(_envelope(product))
    assert await provider.get_price("B09VPHVT9Z") is None


@pytest.mark.asyncio
async def test_get_offers_reads_only_live_offers() -> None:
    # Keepa's `offers` holds every offer ever seen; liveOffersOrder says which
    # are live. A long-gone $35 "new" seller must not be reported.
    product = _product()
    stale = {
        "sellerId": "A1GONE",
        "isAmazon": False,
        "isFBA": True,
        "condition": 1,
        "offerCSV": [_keepa_minutes(_ago(200)), 3500, 0],
    }
    product["offers"] = [*product["offers"], stale]
    product["liveOffersOrder"] = [0, 1, 2]
    offers = await _provider(_envelope(product)).get_offers("B09VPHVT9Z")
    assert all(o.metadata["seller_id"] != "A1GONE" for o in offers)
    assert len(offers) == 3


@pytest.mark.asyncio
async def test_get_offers_without_live_order_drops_offers_not_seen_lately() -> None:
    product = _product()
    product["offers"][1]["lastSeen"] = _keepa_minutes(_ago(30))  # gone for a month
    product["offers"][0]["lastSeen"] = _keepa_minutes(_ago(0.1))
    offers = await _provider(_envelope(product)).get_offers("B09VPHVT9Z")
    sellers = {o.metadata["seller_id"] for o in offers}
    assert "A1THIRDPARTY" not in sellers
    assert "ATVPDKIKX0DER" in sellers


@pytest.mark.asyncio
async def test_history_stats_come_from_the_same_series_as_the_points() -> None:
    # KONG B004VBC0FM: the buy box (deepest series) usually sat at $15.85 while
    # Keepa's AMAZON average was $10.98 — mixing them called a 30% drop "usual".
    product = _product()
    product["csv"][18] = [
        v
        for day, cents in ((80, 1585), (60, 1594), (40, 1585), (20, 1639), (1, 1099))
        for v in (_keepa_minutes(_ago(day)), cents, 0)
    ]
    product["stats"]["avg90"][0] = 1098
    product["stats"]["avg90"][18] = 1570
    history = await _provider(_envelope(product)).get_price_history("B004VBC0FM", days=90)
    assert history is not None
    assert history.metadata["base_kind"] == "buy_box"
    assert history.metadata["keepa_stats"]["avg90_cents"] == 1570

    # No Keepa stat for that series -> None, so the scorer uses the window average.
    product["stats"]["avg90"][18] = -1
    history = await _provider(_envelope(product)).get_price_history("B004VBC0FM", days=90)
    assert history is not None
    assert history.metadata["keepa_stats"]["avg90_cents"] is None


@pytest.mark.asyncio
async def test_product_carries_keepas_matched_ebay_listings() -> None:
    product = _product()
    product["csv"] = product["csv"] + [None] * 15  # room for indices 28 / 29
    product["csv"][28] = [_keepa_minutes(_ago(9)), 3999, 500, _keepa_minutes(_ago(3)), 3549, 0]
    product["csv"][29] = [_keepa_minutes(_ago(9)), 1999, 0, _keepa_minutes(_ago(1)), -1, -1]
    product["ebayListingIds"] = [273344490183, 0]
    product["lastEbayUpdate"] = _keepa_minutes(_ago(1))
    parsed = await _provider(_envelope(product)).get_product("B09VPHVT9Z")
    assert parsed is not None
    ebay = parsed.metadata["ebay"]
    assert ebay["new_cents"] == 3549 and ebay["new_listing_id"] == 273344490183
    # The used listing ended (-1): no current used price, not the stale $19.99.
    assert ebay["used_cents"] is None and ebay["used_listing_id"] is None
    assert ebay["updated_at"]

    plain = await _provider(_envelope(_product())).get_product("B09VPHVT9Z")
    assert plain is not None and plain.metadata["ebay"] is None
