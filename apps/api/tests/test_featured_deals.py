from __future__ import annotations

from collections.abc import Generator
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

ADMIN = {"X-Admin-Token": "dev-admin-token"}
EXPECTED_DEAL_COUNT = 20


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
        assert first["price_checked"] == "2026-08-29"
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
