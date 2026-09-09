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
