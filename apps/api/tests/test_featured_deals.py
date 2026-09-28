from __future__ import annotations

import asyncio
import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.tracking import TrackedProduct
from app.providers.base import (
    ProviderCapability,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderPricePoint,
)
from app.providers.registry import ProviderRegistry
from app.services.tracking.service import run_alert_cycle

ADMIN = {"X-Admin-Token": "dev-admin-token"}
EXPECTED_DEAL_COUNT = 68


def make_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

    def override_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app, follow_redirects=False), session


def test_featured_deals_empty_before_sync() -> None:
    client, session = make_client()
    try:
        body = client.get("/featured-deals").json()
        assert body == {"count": 0, "deals": []}
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_curated_sync_populates_featured_deals() -> None:
    client, session = make_client()
    try:
        sync = client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        assert sync.status_code == 200
        assert sync.json()["provider_source"] == "amazon_ca"
        assert sync.json()["stats"]["received"] == EXPECTED_DEAL_COUNT

        body = client.get("/featured-deals").json()
        assert body["count"] == EXPECTED_DEAL_COUNT
        prices = [deal["price_cents"] for deal in body["deals"]]
        assert prices == sorted(prices), "featured deals are ordered cheapest first"

        first = body["deals"][0]
        assert first["merchant"] == "Amazon.ca"
        assert first["currency"] == "CAD"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", first["price_checked"])
        assert first["blurb"]
        assert first["product_url"].startswith("https://www.amazon.ca/dp/")

        limited = client.get("/featured-deals?limit=3").json()
        assert limited["count"] == 3
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_featured_deal_slug_and_detail_lookup() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        deals = client.get("/featured-deals").json()["deals"]
        slugs = [d["slug"] for d in deals]
        assert all(slugs), "every deal has a slug"
        assert len(set(slugs)) == len(slugs), "slugs are unique"
        assert "-" in slugs[0] and slugs[0] == slugs[0].lower()

        first = deals[0]
        detail = client.get(f"/featured-deals/{first['slug']}")
        assert detail.status_code == 200
        assert detail.json()["offer_id"] == first["offer_id"]
        assert detail.json()["title"] == first["title"]

        assert client.get("/featured-deals/no-such-deal").status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_featured_deal_categories() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        body = client.get("/featured-deals/categories").json()
        assert body["count"] >= 4
        by_slug = {c["slug"]: c for c in body["categories"]}
        assert "electronics" in by_slug
        assert by_slug["electronics"]["count"] >= 1
        assert sum(c["count"] for c in body["categories"]) == EXPECTED_DEAL_COUNT

        elec = client.get("/featured-deals?category=electronics").json()
        assert elec["count"] == by_slug["electronics"]["count"]
        assert all(d["category_slug"] == "electronics" for d in elec["deals"])
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_featured_deal_click_carries_amazon_tag_and_subid() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        offer_id = client.get("/featured-deals").json()["deals"][0]["offer_id"]

        resp = client.get(
            f"/go/{offer_id}?t=affiliate",
            headers={"user-agent": "Mozilla/5.0"},
        )
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://www.amazon.ca/dp/")
        query = parse_qs(urlsplit(location).query)
        assert query["tag"] == ["saveiq-20"]
        assert len(query["ascsubtag"][0]) == 32

        clicks = client.get("/admin/affiliate/clicks", headers=ADMIN).json()
        assert clicks[0]["network"] == "amazon"
    finally:
        app.dependency_overrides.clear()
        session.close()


class _FakeKeepa:
    """Same price, 90-day average and 90-day history for every ASIN.

    The history sits at the average with a dip to ``low_cents`` every ten
    days, so ``low_cents`` is the 90-day low the decision engine sees.
    """

    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset({ProviderCapability.get_price, ProviderCapability.price_history})

    def __init__(
        self, price_cents: int | None, avg90_cents: int, low_cents: int | None = None
    ) -> None:
        self._price = price_cents
        self._avg90 = avg90_cents
        self._low = low_cents if low_cents is not None else (price_cents or avg90_cents)
        self.prefetched: list[str] = []

    def is_configured(self) -> bool:
        return True

    async def prefetch_products(self, asins: list[str], *, stats_days: int = 90) -> int:
        self.prefetched.extend(asins)
        return len(asins)

    async def get_price(self, pid: str) -> ProviderPrice | None:
        if self._price is None:  # no current offer
            return None
        return ProviderPrice(
            provider="keepa",
            provider_product_id=pid,
            price_cents=self._price,
            currency="CAD",
            observed_at=datetime.now(tz=UTC),
            source="keepa:buy_box",
        )

    async def get_price_history(self, pid: str, *, days: int = 180) -> ProviderPriceHistory | None:
        return ProviderPriceHistory(
            provider="keepa",
            provider_product_id=pid,
            currency="CAD",
            points=[
                ProviderPricePoint(
                    observed_at=datetime.now(tz=UTC) - timedelta(days=day),
                    price_cents=self._low if day % 10 == 0 else self._avg90,
                    kind="buy_box",
                )
                for day in range(89, 0, -1)
            ],
            metadata={"keepa_stats": {"avg90_cents": self._avg90}},
        )


class _NoEmail:
    def send(self, message: object) -> None:
        raise AssertionError("no alerts exist, so no email should be sent")


def _poll(session: Session, keepa: _FakeKeepa, *, now: datetime | None = None) -> None:
    registry = ProviderRegistry()
    registry.register(keepa)
    asyncio.run(run_alert_cycle(session, registry, email_sender=_NoEmail(), now=now))
    session.commit()


def test_price_drops_empty_before_any_poll() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        assert client.get("/featured-deals/price-drops").json() == {"count": 0, "deals": []}
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_daily_poll_tracks_curated_products_and_lists_drops() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        keepa = _FakeKeepa(price_cents=4500, avg90_cents=5000)  # 10% under average
        _poll(session, keepa)

        assert len(set(keepa.prefetched)) == EXPECTED_DEAL_COUNT, "one batched prefetch"

        body = client.get("/featured-deals/price-drops?limit=5").json()
        assert body["count"] == 5
        latest = body["deals"][0]["latest_price"]
        assert latest["price_cents"] == 4500
        assert latest["avg90_cents"] == 5000
        assert latest["pct_below_avg90"] == 10
        assert latest["verdict"] == "BUY"

        slug = body["deals"][0]["slug"]
        detail = client.get(f"/featured-deals/{slug}").json()
        assert detail["latest_price"]["price_cents"] == 4500
        listed = client.get("/featured-deals?limit=1").json()["deals"][0]
        assert listed["latest_price"]["pct_below_avg90"] == 10

        # Re-running the cycle does not duplicate the tracked products.
        _poll(session, keepa)
        assert session.query(TrackedProduct).count() == EXPECTED_DEAL_COUNT
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_small_dips_are_not_price_drops() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        _poll(session, _FakeKeepa(price_cents=4900, avg90_cents=5000))  # only 2% under
        assert client.get("/featured-deals/price-drops").json()["count"] == 0
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_drops_far_above_the_90_day_low_are_not_listed() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        # 10% under a (skewed) average, but the product regularly sells for
        # $30 — so $45 is nowhere near its usual low and must not be a "drop".
        _poll(session, _FakeKeepa(price_cents=4500, avg90_cents=5000, low_cents=3000))
        assert client.get("/featured-deals/price-drops").json()["count"] == 0
        listed = client.get("/featured-deals?limit=1").json()["deals"][0]
        assert listed["latest_price"]["pct_below_avg90"] == 10
        assert listed["latest_price"]["verdict"] != "BUY"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_a_later_check_with_no_offer_hides_the_old_price() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        _poll(
            session,
            _FakeKeepa(price_cents=4500, avg90_cents=5000),
            now=datetime.now(tz=UTC) - timedelta(hours=2),
        )
        assert client.get("/featured-deals/price-drops").json()["count"] > 0

        _poll(session, _FakeKeepa(price_cents=None, avg90_cents=5000))  # now out of stock
        assert client.get("/featured-deals/price-drops").json()["count"] == 0
        listed = client.get("/featured-deals?limit=1").json()["deals"][0]
        assert listed["latest_price"] is None
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_stale_readings_are_not_price_drops() -> None:
    client, session = make_client()
    try:
        client.post("/admin/affiliate/sync/curated", headers=ADMIN)
        _poll(
            session,
            _FakeKeepa(price_cents=4000, avg90_cents=5000),
            now=datetime.now(tz=UTC) - timedelta(days=3),
        )
        assert client.get("/featured-deals/price-drops").json()["count"] == 0
        # The reading still shows on the deal itself, with its real date.
        listed = client.get("/featured-deals?limit=1").json()["deals"][0]
        assert listed["latest_price"]["pct_below_avg90"] == 20
    finally:
        app.dependency_overrides.clear()
        session.close()
