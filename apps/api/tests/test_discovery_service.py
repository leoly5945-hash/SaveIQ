"""Discovery service: search + optional budget probe."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.providers.base import ProviderCapability, ProviderPrice, ProviderProduct
from app.providers.registry import ProviderRegistry
from app.services.discovery import discover
from app.services.discovery.query import parse_shopping_query

NOW = datetime(2026, 9, 9, tzinfo=UTC)


class FakeKeepa:
    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset(
        {ProviderCapability.search, ProviderCapability.get_price, ProviderCapability.get_product}
    )

    def __init__(self, catalogue: dict[str, int]) -> None:
        # asin -> price cents (search returns them all; get_price returns the map)
        self._catalogue = catalogue
        self.searched: list[str] = []
        self.priced: list[str] = []

    def is_configured(self) -> bool:
        return True

    async def search_products(self, query: str, *, limit: int = 10) -> list[ProviderProduct]:
        self.searched.append(query)
        return [
            ProviderProduct(
                provider="keepa",
                provider_product_id=asin,
                title=f"Item {asin}",
                brand="Acme",
                market="CA",
                currency="CAD",
            )
            for asin in list(self._catalogue)[:limit]
        ]

    async def get_price(self, asin: str) -> ProviderPrice | None:
        self.priced.append(asin)
        cents = self._catalogue.get(asin)
        if cents is None:
            return None
        return ProviderPrice(
            provider="keepa",
            provider_product_id=asin,
            price_cents=cents,
            currency="CAD",
            observed_at=NOW,
            source="keepa:buy_box",
        )


def _reg(adapter: object) -> ProviderRegistry:
    r = ProviderRegistry()
    r.register(adapter)
    return r


@pytest.mark.asyncio
async def test_no_budget_still_prices_and_sorts_cheapest_first() -> None:
    # discovery is a storefront — every row needs a price even without a budget
    fake = FakeKeepa({"B01": 9000, "B02": 5000})
    q = parse_shopping_query("power bank")
    res = await discover(_reg(fake), q, limit=8)
    assert res.price_probed is True
    assert set(fake.priced) == {"B01", "B02"}
    assert [h.product_id for h in res.hits] == ["B02", "B01"]  # price asc
    assert [h.price_cents for h in res.hits] == [5000, 9000]
    assert all(h.in_budget is None for h in res.hits)  # no budget -> no verdict


@pytest.mark.asyncio
async def test_unpriced_rows_sort_last() -> None:
    fake = FakeKeepa({"B01": 7000, "B02": None})  # B02 has no price
    q = parse_shopping_query("power bank")
    res = await discover(_reg(fake), q, limit=8)
    ids = [h.product_id for h in res.hits]
    assert ids == ["B01", "B02"]
    assert res.hits[-1].price_cents is None


@pytest.mark.asyncio
async def test_budget_probes_and_sorts_in_budget_first() -> None:
    fake = FakeKeepa({"B01": 12000, "B02": 8000, "B03": 9500})
    q = parse_shopping_query("power bank under $100")
    res = await discover(_reg(fake), q, limit=8)
    assert res.price_probed is True
    assert q.price_max_cents == 10000
    ids = [h.product_id for h in res.hits]
    assert ids[0] == "B02" and ids[1] == "B03"  # in budget, price asc
    assert ids[2] == "B01"  # over budget last
    assert res.hits[0].in_budget is True
    assert res.hits[2].in_budget is False


@pytest.mark.asyncio
async def test_empty_when_no_search_capable_provider() -> None:
    r = ProviderRegistry()
    res = await discover(r, parse_shopping_query("anything"), limit=5)
    assert res.hits == [] and res.price_probed is False
