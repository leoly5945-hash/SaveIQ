from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app


def make_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()

    def override_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), session


def test_search_returns_normalized_mock_offers() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)

        response = client.get("/search?q=buds")

        assert response.status_code == 200
        payload = response.json()
        assert payload["query"] == "buds"
        assert payload["count"] == 2
        assert {result["merchant"] for result in payload["results"]} == {
            "Maple Tech",
            "North Outfitters",
        }
        first_sale_price = payload["results"][0]["sale_price_cents"]
        second_sale_price = payload["results"][1]["sale_price_cents"]
        assert first_sale_price <= second_sale_price
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_search_matches_terms_instead_of_requiring_exact_phrase() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)

        response = client.get("/search?q=wireless%20earbuds")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 2
        assert all("Earbuds" in result["offer_title"] for result in payload["results"])
        assert all("product title" in result["match_reasons"] for result in payload["results"])
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_search_filters_coupon_cashback_and_freshness() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)

        coupon_response = client.get("/search?has_coupon=true")
        cashback_response = client.get("/search?has_cashback=true")
        freshness_response = client.get("/search?freshness=fresh")

        assert coupon_response.status_code == 200
        assert all(result["has_coupon"] for result in coupon_response.json()["results"])
        assert cashback_response.status_code == 200
        assert all(result["has_cashback"] for result in cashback_response.json()["results"])
        assert freshness_response.status_code == 200
        assert all(
            result["freshness_status"] == "fresh" for result in freshness_response.json()["results"]
        )
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_search_rejects_unknown_freshness() -> None:
    client, session = make_client()
    try:
        response = client.get("/search?freshness=live")

        assert response.status_code == 422
        assert "freshness must be one of" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_search_sorts_by_highest_current_price() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)

        response = client.get("/search?q=buds&sort=price_desc")

        assert response.status_code == 200
        payload = response.json()
        prices = [
            result["sale_price_cents"] or result["price_cents"] for result in payload["results"]
        ]
        assert prices == sorted(prices, reverse=True)
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_search_expands_backpack_to_pack() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)

        response = client.get("/search?q=backpack")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] >= 1
        assert any("Trail Pack" in result["title"] for result in payload["results"])
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_search_rejects_unknown_sort() -> None:
    client, session = make_client()
    try:
        response = client.get("/search?sort=random")

        assert response.status_code == 422
        assert "sort must be one of" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_offer_detail_returns_source_attribution_and_commercial_context() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)
        search_response = client.get("/search?q=buds")
        offer_id = search_response.json()["results"][0]["offer_id"]

        response = client.get(f"/search/offers/{offer_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["offer_id"] == offer_id
        assert payload["affiliate_url"].startswith("https://affiliate.example.test/")
        assert payload["source_attribution"]["provider_source"] == "mock_ca"
        assert payload["source_attribution"]["source_record_id"]
        assert payload["price_history"]
        assert payload["coupons"] or payload["cashback_offers"]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_offer_detail_returns_404_for_unknown_offer() -> None:
    client, session = make_client()
    try:
        response = client.get("/search/offers/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Offer not found"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_click_tracking_records_product_clicks_for_active_offers() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)
        search_response = client.get("/search?q=buds")
        offer_id = search_response.json()["results"][0]["offer_id"]

        response = client.post(
            "/clicks",
            headers={"user-agent": "pytest"},
            json={
                "offer_id": offer_id,
                "target_type": "product",
                "referrer": "https://dealhunter-staging-web.onrender.com/",
            },
        )
        clicks_response = client.get("/admin/affiliate/clicks", headers=headers)

        assert response.status_code == 201
        payload = response.json()
        assert payload["offer_id"] == offer_id
        assert payload["target_type"] == "product"
        assert payload["target_url"].startswith("https://maple-tech.example.test/products/")
        assert clicks_response.status_code == 200
        clicks = clicks_response.json()
        assert clicks[0]["offer_id"] == offer_id
        assert clicks[0]["target_type"] == "product"
        assert clicks[0]["referrer"] == "https://dealhunter-staging-web.onrender.com/"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_click_tracking_rejects_unknown_target_type() -> None:
    client, session = make_client()
    try:
        response = client.post(
            "/clicks",
            json={"offer_id": 1, "target_type": "checkout"},
        )

        assert response.status_code == 422
        assert "target_type must be one of" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_click_tracking_returns_404_for_unknown_offer() -> None:
    client, session = make_client()
    try:
        response = client.post(
            "/clicks",
            json={"offer_id": 999, "target_type": "product"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Trackable offer target not found"
    finally:
        app.dependency_overrides.clear()
        session.close()
