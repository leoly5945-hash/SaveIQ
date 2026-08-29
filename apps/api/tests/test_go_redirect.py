from collections.abc import Generator
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.settings import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

ADMIN = {"X-Admin-Token": "dev-admin-token"}


def make_client(**settings_overrides: object) -> tuple[TestClient, Session]:
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
    if settings_overrides:
        patched = get_settings().model_copy(update=dict(settings_overrides))
        app.dependency_overrides[get_settings] = lambda: patched
    return TestClient(app, follow_redirects=False), session


def _seed_offer(client: TestClient) -> int:
    assert client.post("/admin/affiliate/sync/mock", headers=ADMIN).status_code == 200
    offers = client.get("/admin/affiliate/offers", headers=ADMIN).json()
    return int(offers[0]["id"])


def test_go_redirect_logs_click_and_appends_subid() -> None:
    client, session = make_client()
    try:
        offer_id = _seed_offer(client)
        resp = client.get(f"/go/{offer_id}?t=product", headers={"user-agent": "Mozilla/5.0"})
        assert resp.status_code == 302
        location = resp.headers["location"]
        query = parse_qs(urlsplit(location).query)
        subid = query["subid"][0]
        assert len(subid) == 32
        assert resp.headers["x-robots-tag"].startswith("noindex")

        clicks = client.get("/admin/affiliate/clicks", headers=ADMIN).json()
        assert len(clicks) == 1
        row = clicks[0]
        assert row["click_id"] == subid
        assert row["subid"] == subid
        assert row["network"] == "mock"
        assert row["is_bot"] is False
        assert row["landing_url"] == location
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_go_flags_bot_user_agent() -> None:
    client, session = make_client()
    try:
        offer_id = _seed_offer(client)
        resp = client.get(f"/go/{offer_id}", headers={"user-agent": "python-requests/2.31"})
        assert resp.status_code == 302
        clicks = client.get("/admin/affiliate/clicks", headers=ADMIN).json()
        assert clicks[0]["is_bot"] is True
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_go_dedups_rapid_repeat_clicks() -> None:
    client, session = make_client()
    try:
        offer_id = _seed_offer(client)
        headers = {"user-agent": "Mozilla/5.0", "x-forwarded-for": "203.0.113.9"}
        first = client.get(f"/go/{offer_id}?t=product", headers=headers)
        second = client.get(f"/go/{offer_id}?t=product", headers=headers)
        assert first.headers["location"] == second.headers["location"]
        clicks = client.get("/admin/affiliate/clicks", headers=ADMIN).json()
        assert len(clicks) == 1
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_go_unknown_offer_is_404() -> None:
    client, session = make_client()
    try:
        assert client.get("/go/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_postback_matches_conversion_and_reconciliation() -> None:
    client, session = make_client(affiliate_postback_secret="s3cr3t")
    try:
        offer_id = _seed_offer(client)
        redirect = client.get(f"/go/{offer_id}?t=product", headers={"user-agent": "Mozilla/5.0"})
        subid = parse_qs(urlsplit(redirect.headers["location"]).query)["subid"][0]

        unauthorized = client.post("/affiliate/postback/mock", json={"subid": subid})
        assert unauthorized.status_code == 401

        ok = client.post(
            "/affiliate/postback/mock?secret=s3cr3t",
            json={
                "subid": subid,
                "conversion_id": "MOCK-1",
                "sale_amount": "129.99",
                "commission": "6.50",
                "currency": "cad",
                "status": "approved",
            },
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["matched_click_event_id"] is not None
        assert body["status"] == "approved"

        recon = client.get("/admin/affiliate/reconciliation", headers=ADMIN).json()
        assert recon["totals"]["conversions"] == 1
        row = next(r for r in recon["rows"] if r["network"] == "mock")
        assert row["clicks"] == 1
        assert row["conversions"] == 1
        assert row["conversion_rate"] == 1.0
        assert row["commission_cents"] == 650
        assert row["order_value_cents"] == 12999

        # Idempotent: same external_id updates in place, no double count.
        again = client.post(
            "/affiliate/postback/mock?secret=s3cr3t",
            json={"subid": subid, "conversion_id": "MOCK-1", "status": "reversed"},
        )
        assert again.status_code == 200
        recon2 = client.get("/admin/affiliate/reconciliation", headers=ADMIN).json()
        assert recon2["totals"]["conversions"] == 0
    finally:
        app.dependency_overrides.clear()
        session.close()
