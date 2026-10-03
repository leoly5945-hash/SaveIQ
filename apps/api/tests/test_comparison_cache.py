"""Unit tests for the task-backed cross-merchant comparison cache."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.comparison import ComparisonStatus, MerchantComparison
from app.providers.base import ProviderOffer
from app.providers.registry import ProviderRegistry
from app.services.decision.comparison_cache import (
    poll_pending_comparisons,
    resolve_comparison,
    resolve_merchant_links,
    shopping_keyword,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


class FakeDFS:
    name = "dataforseo"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset()

    def __init__(self, *, ready_after: int = 0, offers: list[ProviderOffer] | None = None) -> None:
        self._ready_after = ready_after
        self._fetches = 0
        self._offers = offers
        self.submitted: list[str] = []
        self.raise_on_submit = False

    def is_configured(self) -> bool:
        return True

    async def submit_offers_task(self, keyword: str) -> str:
        if self.raise_on_submit:
            raise RuntimeError("boom")
        self.submitted.append(keyword)
        return f"task-{len(self.submitted)}"

    async def fetch_offers_task(
        self, task_id: str, *, provider_product_id: str | None = None
    ) -> list[ProviderOffer] | None:
        self._fetches += 1
        if self._fetches <= self._ready_after:
            return None
        if self._offers is not None:
            return self._offers
        return [
            ProviderOffer(
                provider="dataforseo",
                provider_product_id=provider_product_id or "ref",
                merchant="Walmart Canada",
                price_cents=3999,
                currency="CAD",
                url="https://walmart.ca/x",
                observed_at=NOW,
                metadata={"title": "Anker 737 Power Bank"},
            )
        ]


def _registry(dfs: object | None) -> ProviderRegistry:
    reg = ProviderRegistry()
    if dfs is not None:
        reg.register(dfs)
    return reg


@pytest.mark.parametrize(
    ("title", "brand", "expected"),
    [
        (
            "Amazon Echo Dot (newest model), Vibrant sounding Alexa speaker, Great for bedrooms",
            "Amazon",
            "Amazon Echo Dot",
        ),
        (
            "Anker Prime Power Bank, 20,100mAh 3-Port Portable Charger",
            None,
            "Anker Prime Power Bank",
        ),
        ("SanDisk 1TB Extreme Portable SSD", "SanDisk", "SanDisk 1TB Extreme Portable SSD"),
        ("Sony WH-1000XM5", "Sony", "Sony WH-1000XM5"),
    ],
)
def test_shopping_keyword(title: str, brand: str | None, expected: str) -> None:
    assert shopping_keyword(title, brand) == expected


def test_shopping_keyword_prepends_missing_brand() -> None:
    assert shopping_keyword("737 Power Bank PowerCore", "Anker").startswith("Anker 737")


@pytest.mark.asyncio
async def test_resolve_cold_submits_task_and_returns_none(db: Session) -> None:
    dfs = FakeDFS()
    out = await resolve_comparison(
        db,
        _registry(dfs),
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        title="Anker 737 Power Bank, huge battery",
        brand=None,
        currency="CAD",
        now=NOW,
    )
    assert out is None
    assert dfs.submitted == ["Anker 737 Power Bank"]
    row = db.query(MerchantComparison).one()
    assert row.status == ComparisonStatus.pending.value
    assert row.task_id == "task-1"


@pytest.mark.asyncio
async def test_resolve_no_provider_returns_none(db: Session) -> None:
    out = await resolve_comparison(
        db,
        _registry(None),
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        title="Anker 737",
        brand=None,
        currency="CAD",
        now=NOW,
    )
    assert out is None
    assert db.query(MerchantComparison).count() == 0


@pytest.mark.asyncio
async def test_resolve_polls_pending_after_min_age_and_caches(db: Session) -> None:
    dfs = FakeDFS()
    reg = _registry(dfs)
    kwargs = dict(
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        title="Anker 737 Power Bank",
        brand=None,
        currency="CAD",
    )
    await resolve_comparison(db, reg, now=NOW, **kwargs)  # submits
    # too soon: still within _MIN_POLL_AGE
    assert await resolve_comparison(db, reg, now=NOW + timedelta(seconds=5), **kwargs) is None
    # later: polls, gets offers, caches
    later = NOW + timedelta(seconds=30)
    out = await resolve_comparison(db, reg, now=later, **kwargs)
    assert out is not None and out[0].merchant == "Walmart Canada"
    row = db.query(MerchantComparison).one()
    assert row.status == ComparisonStatus.ready.value
    assert row.expires_at is not None
    # next call within TTL is served straight from cache (no extra fetch)
    fetches = dfs._fetches
    again = await resolve_comparison(db, reg, now=later + timedelta(hours=1), **kwargs)
    assert again is not None
    assert dfs._fetches == fetches


@pytest.mark.asyncio
async def test_resolve_marks_failed_after_pending_timeout(db: Session) -> None:
    dfs = FakeDFS(ready_after=100)  # never ready
    reg = _registry(dfs)
    kwargs = dict(
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        title="Anker 737 Power Bank",
        brand=None,
        currency="CAD",
    )
    await resolve_comparison(db, reg, now=NOW, **kwargs)
    out = await resolve_comparison(db, reg, now=NOW + timedelta(minutes=45), **kwargs)
    assert out is None
    row = db.query(MerchantComparison).one()
    assert row.status == ComparisonStatus.failed.value


@pytest.mark.asyncio
async def test_resolve_swallows_submit_error(db: Session) -> None:
    dfs = FakeDFS()
    dfs.raise_on_submit = True
    out = await resolve_comparison(
        db,
        _registry(dfs),
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        title="Anker 737 Power Bank",
        brand=None,
        currency="CAD",
        now=NOW,
    )
    assert out is None
    assert db.query(MerchantComparison).count() == 0


@pytest.mark.asyncio
async def test_poll_pending_completes_and_reports(db: Session) -> None:
    dfs = FakeDFS()
    reg = _registry(dfs)
    kwargs = dict(
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        title="Anker 737 Power Bank",
        brand=None,
        currency="CAD",
    )
    await resolve_comparison(db, reg, now=NOW, **kwargs)  # one pending row
    stats = await poll_pending_comparisons(db, reg, now=NOW + timedelta(seconds=30))
    assert stats.pending_seen == 1
    assert stats.completed == 1
    row = db.query(MerchantComparison).one()
    assert row.status == ComparisonStatus.ready.value


# -- store links (Sellers lookup for the offers that are shown) ---------------

GOOGLE_URL = "https://www.google.ca/search?ibp=oshop&q=anker&prds=pid:111"


class FakeSellersDFS(FakeDFS):
    def __init__(self, shops: list[dict[str, str | None]] | None) -> None:
        super().__init__(
            offers=[
                ProviderOffer(
                    provider="dataforseo",
                    provider_product_id="B01",
                    merchant="Walmart Canada",
                    price_cents=3999,
                    currency="CAD",
                    url=GOOGLE_URL,
                    observed_at=NOW,
                    metadata={"title": "Anker 737 Power Bank", "product_id": 111, "gid": None},
                )
            ]
        )
        self._shops = shops
        self.seller_tasks: list[dict[str, str | None]] = []
        self.seller_fetches = 0

    async def submit_sellers_task(
        self, *, product_id: str | None, data_docid: str | None, gid: str | None
    ) -> str:
        self.seller_tasks.append({"product_id": product_id, "data_docid": data_docid, "gid": gid})
        return "sellers-1"

    async def fetch_sellers_task(self, task_id: str) -> list[dict[str, str | None]] | None:
        self.seller_fetches += 1
        return self._shops


async def _ready_row(db: Session, reg: ProviderRegistry, *, at: datetime) -> dict:
    kwargs = dict(
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        title="Anker 737 Power Bank",
        brand=None,
        currency="CAD",
    )
    await resolve_comparison(db, reg, now=at, **kwargs)
    await resolve_comparison(db, reg, now=at + timedelta(seconds=30), **kwargs)
    return kwargs


@pytest.mark.asyncio
async def test_store_link_is_looked_up_once_then_served(db: Session) -> None:
    dfs = FakeSellersDFS(
        [
            {"seller_name": "Other Shop", "url": "https://other.example/p", "domain": None},
            {
                "seller_name": "Walmart Canada",
                "url": "https://www.walmart.ca/en/ip/anker/123?srsltid=zz",
                "domain": "www.walmart.ca",
            },
        ]
    )
    reg = _registry(dfs)
    kwargs = await _ready_row(db, reg, at=NOW)
    link_kwargs = dict(provider="keepa", provider_product_id="B01", market="CA")
    t1 = NOW + timedelta(minutes=1)

    # first view: a Sellers task is submitted, nothing to show yet
    assert (
        await resolve_merchant_links(db, reg, shown_urls=[GOOGLE_URL], now=t1, **link_kwargs) == {}
    )
    assert dfs.seller_tasks == [{"product_id": "111", "data_docid": None, "gid": None}]
    # too soon to poll
    soon = t1 + timedelta(seconds=5)
    assert (
        await resolve_merchant_links(db, reg, shown_urls=[GOOGLE_URL], now=soon, **link_kwargs)
        == {}
    )
    assert dfs.seller_fetches == 0
    # later view: the store link is found and cached
    t2 = t1 + timedelta(seconds=40)
    found = await resolve_merchant_links(db, reg, shown_urls=[GOOGLE_URL], now=t2, **link_kwargs)
    assert found == {GOOGLE_URL: "https://www.walmart.ca/en/ip/anker/123"}

    offers = await resolve_comparison(db, reg, now=t2, **kwargs)
    assert offers is not None and offers[0].url == "https://www.walmart.ca/en/ip/anker/123"
    # served from the row from now on: no further Sellers calls
    assert (
        await resolve_merchant_links(db, reg, shown_urls=[GOOGLE_URL], now=t2, **link_kwargs) == {}
    )
    assert len(dfs.seller_tasks) == 1 and dfs.seller_fetches == 1

    # a daily refresh of the same listing keeps the link instead of paying again
    next_day = t2 + timedelta(hours=25)
    await resolve_comparison(db, reg, now=next_day, **kwargs)
    refreshed = await resolve_comparison(db, reg, now=next_day + timedelta(seconds=30), **kwargs)
    assert refreshed is not None and refreshed[0].url == "https://www.walmart.ca/en/ip/anker/123"
    assert len(dfs.seller_tasks) == 1


@pytest.mark.asyncio
async def test_store_link_no_matching_seller_keeps_google_link(db: Session) -> None:
    dfs = FakeSellersDFS(
        [
            {
                "seller_name": "Walmart Canada",
                "url": "https://www.google.ca/aclk?ai=1",
                "domain": None,
            }
        ]
    )
    reg = _registry(dfs)
    kwargs = await _ready_row(db, reg, at=NOW)
    link_kwargs = dict(provider="keepa", provider_product_id="B01", market="CA")
    t1 = NOW + timedelta(minutes=1)
    await resolve_merchant_links(db, reg, shown_urls=[GOOGLE_URL], now=t1, **link_kwargs)
    t2 = t1 + timedelta(seconds=40)
    assert (
        await resolve_merchant_links(db, reg, shown_urls=[GOOGLE_URL], now=t2, **link_kwargs) == {}
    )
    offers = await resolve_comparison(db, reg, now=t2, **kwargs)
    assert offers is not None and offers[0].url == GOOGLE_URL
    # not retried on every view
    await resolve_merchant_links(db, reg, shown_urls=[GOOGLE_URL], now=t2, **link_kwargs)
    assert len(dfs.seller_tasks) == 1 and dfs.seller_fetches == 1


@pytest.mark.asyncio
async def test_store_link_skips_offers_that_are_not_shown(db: Session) -> None:
    dfs = FakeSellersDFS([])
    reg = _registry(dfs)
    await _ready_row(db, reg, at=NOW)
    out = await resolve_merchant_links(
        db,
        reg,
        provider="keepa",
        provider_product_id="B01",
        market="CA",
        shown_urls=[],
        now=NOW + timedelta(minutes=1),
    )
    assert out == {} and dfs.seller_tasks == []
