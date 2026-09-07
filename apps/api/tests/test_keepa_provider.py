"""Unit tests for :class:`app.providers.keepa.KeepaProvider`.

All Keepa responses here are synthetic dev fixtures built in-process — no network
call is made. Timestamps are derived from a pinned ``NOW`` so the trailing-window
filter is deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.providers.base import ProviderCapability, ProviderError
from app.providers.keepa import _KEEPA_EPOCH_OFFSET_MINUTES, KeepaProvider

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
async def test_get_price_history_decodes_and_filters() -> None:
    provider = _provider(_envelope(_product()))
    history = await provider.get_price_history("B09VPHVT9Z", days=30)
    assert history is not None
    assert history.currency == "CAD"
    assert history.points, "expected decoded points"

    kinds = {p.kind for p in history.points}
    assert "amazon" in kinds
    assert "buy_box" in kinds
    # The USED point is ~45 days old and must be filtered out by the 30d window.
    assert "used" not in kinds
    # The 60-day-old AMAZON point is filtered; the 20d + 2d ones remain.
    amazon_points = [p for p in history.points if p.kind == "amazon"]
    assert [p.price_cents for p in amazon_points] == [4599, 4299]

    assert history.points == sorted(history.points, key=lambda p: (p.observed_at, p.kind))
    assert history.covers_from is not None and history.covers_to is not None
    assert history.metadata["keepa_stats"]["min_cents"] == 4299
    assert history.metadata["keepa_stats"]["max_cents"] == 4999
    assert history.metadata["keepa_stats"]["avg90_cents"] == 4650


@pytest.mark.asyncio
async def test_price_history_tolerates_malformed_csv_slots() -> None:
    product = _product(with_offers=False)
    # Real Keepa never sends null inside a csv row, but a defensive decode must
    # not raise if it does — skip the bad slot, keep the good ones.
    product["csv"][0] = [
        _keepa_minutes(_ago(10)),
        None,  # malformed price
        _keepa_minutes(_ago(5)),
        4400,
        "oops",  # malformed time
        4300,
    ]
    provider = _provider(_envelope(product))
    history = await provider.get_price_history("B09VPHVT9Z", days=90)
    assert history is not None
    amazon = [p.price_cents for p in history.points if p.kind == "amazon"]
    assert amazon == [4400]


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
