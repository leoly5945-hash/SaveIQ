from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.providers.base import ProviderOffer
from app.providers.ebay_browse import EbayBrowseClient
from app.services.decision import price_check
from app.services.decision.matching import build_comparison


def _item(
    price: str = "19.99",
    *,
    ship: str | None = "0.00",
    currency: str = "CAD",
    condition: str = "1000",
    pct: str = "99.6",
    score: int = 1200,
    title: str = "Logitech M185 Wireless Mouse Grey",
    affiliate: bool = True,
) -> dict:
    item = {
        "title": title,
        "conditionId": condition,
        "price": {"value": price, "currency": currency},
        "seller": {"feedbackPercentage": pct, "feedbackScore": score},
        "itemWebUrl": "https://www.ebay.ca/itm/123",
        "shippingOptions": (
            [{"shippingCost": {"value": ship, "currency": "CAD"}}] if ship is not None else []
        ),
    }
    if affiliate:
        item["itemAffiliateWebUrl"] = "https://www.ebay.ca/itm/123?mkcid=1&campid=5339209072"
    return item


class _Ebay:
    def __init__(self, items: list[dict], *, fail: bool = False) -> None:
        self.items = items
        self.fail = fail
        self.token_calls = 0
        self.search_calls: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": "t0k", "expires_in": 7200})
        self.search_calls.append(request)
        if self.fail:
            return httpx.Response(500)
        return httpx.Response(200, json={"itemSummaries": self.items})

    def client(self, **kw) -> EbayBrowseClient:
        return EbayBrowseClient(
            "id",
            "secret",
            campaign_id="5339209072",
            transport=httpx.MockTransport(self.handler),
            **kw,
        )


@pytest.mark.asyncio
async def test_keeps_only_new_cad_shipped_well_rated_offers() -> None:
    fake = _Ebay(
        [
            _item("19.99", ship="2.50"),
            _item("9.99", condition="3000"),  # used
            _item("8.99", currency="USD"),
            _item("7.99", ship=None),  # unknown shipping -> can't state a total
            _item("6.99", pct="91.0"),  # weak seller
            _item("5.99", score=3),  # too few ratings
        ]
    )
    offers = await fake.client().new_offers(
        provider_product_id="B0052EH8OA", gtin="097855066701", title="x"
    )
    assert [(o.price_cents, o.shipping_cents, o.total_cents) for o in offers] == [(1999, 250, 2249)]
    o = offers[0]
    assert o.condition == "new"
    assert o.url and "campid=5339209072" in o.url
    assert o.metadata["matched_by"] == "gtin"
    req = fake.search_calls[0]
    assert req.url.params["gtin"] == "097855066701"
    assert "conditionIds:{1000}" in req.url.params["filter"]
    assert "itemLocationCountry:CA" in req.url.params["filter"]
    assert req.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_CA"
    assert req.headers["X-EBAY-C-ENDUSERCTX"] == "affiliateCampaignId=5339209072"


@pytest.mark.asyncio
async def test_title_search_when_no_gtin_and_results_are_cached() -> None:
    fake = _Ebay([_item()])
    client = fake.client()
    for _ in range(2):
        offers = await client.new_offers(
            provider_product_id="B1", gtin=None, title="Logitech M185 Wireless Mouse Grey"
        )
        assert offers and offers[0].metadata["matched_by"] == "q"
    assert len(fake.search_calls) == 1
    assert fake.token_calls == 1
    assert fake.search_calls[0].url.params["q"].startswith("Logitech M185")


@pytest.mark.asyncio
async def test_errors_mean_no_offers_not_a_crash() -> None:
    offers = (
        await _Ebay([], fail=True)
        .client()
        .new_offers(provider_product_id="B1", gtin="1", title="x")
    )
    assert offers == []


def _offer(provider: str, merchant: str, cents: int, title: str, **meta) -> ProviderOffer:
    return ProviderOffer(
        provider=provider,
        provider_product_id="B0052EH8OA",
        merchant=merchant,
        price_cents=cents,
        currency="CAD",
        url="https://www.ebay.ca/itm/1",
        observed_at=datetime(2026, 9, 30, tzinfo=UTC),
        metadata={"title": title, **meta},
    )


def test_gtin_match_is_confident_and_carries_seller_detail() -> None:
    ebay = _offer(
        "ebay",
        "eBay",
        2199,
        "Logitech M185 Mouse",
        matched_by="gtin",
        seller_feedback_pct=99.6,
        seller_feedback_score=1200,
    )
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title="Logitech M185 Wireless Mouse Grey",
        reference_brand="Logitech",
        reference_price_cents=2399,
        currency="CAD",
        candidates=[ebay],
    )
    assert comp.cheapest is not None and comp.cheapest.merchant == "eBay"
    assert comp.cheapest.match_confidence >= 0.9
    assert comp.cheapest.detail == (
        "New · ships from Canada · seller 99.6% positive (1,200 ratings)"
    )


@pytest.mark.asyncio
async def test_google_shopping_ebay_rows_are_replaced_by_browse_offers(monkeypatch) -> None:
    google_rows = [
        _offer("dataforseo", "eBay - starbasec3", 1133, "Logitech M185 Wireless Mouse Grey"),
        _offer("dataforseo", "Walmart.ca", 2299, "Logitech M185 Wireless Mouse Grey"),
    ]

    async def fake_resolve(*a, **kw):
        return google_rows

    class FakeEbay:
        async def new_offers(self, **kw):
            return [
                _offer(
                    "ebay",
                    "eBay",
                    2199,
                    "Logitech M185 Wireless Mouse",
                    matched_by="gtin",
                    seller_feedback_pct=99.6,
                    seller_feedback_score=1200,
                    affiliate=True,
                )
            ]

    monkeypatch.setattr(price_check, "resolve_comparison", fake_resolve)
    comp = await price_check._build_comparison(
        None,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        reference_provider="keepa",
        provider_product_id="B0052EH8OA",
        market="CA",
        title="Logitech M185 Wireless Mouse Grey",
        brand="Logitech",
        reference_price_cents=2399,
        currency="CAD",
        ebay_campaign_id="5339209072",
        ebay=FakeEbay(),  # type: ignore[arg-type]
        gtin="097855066701",
    )
    assert comp is not None
    merchants = {o.merchant: o.price_cents for o in comp.offers}
    assert "eBay - starbasec3" not in merchants
    assert merchants == {"eBay": 2199, "Walmart.ca": 2299}
