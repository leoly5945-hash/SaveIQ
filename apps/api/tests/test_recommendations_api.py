from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import RecommendationFeedbackEvent, RecommendationTraceEvent


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


def test_recommendations_return_mock_offers_with_evaluation_trace() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)

        response = client.post(
            "/recommendations",
            json={"intent": "Find fresh wireless earbuds with a coupon", "limit": 3},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["strategy"] == "rule_based_mock_v0"
        assert isinstance(payload["trace_event_id"], int)
        assert payload["intent"]["raw_intent"] == "Find fresh wireless earbuds with a coupon"
        assert payload["intent"]["search_query"] == "wireless earbuds"
        assert payload["intent"]["has_coupon"] is True
        assert payload["intent"]["freshness"] == "fresh"
        assert payload["count"] == 1
        assert payload["recommendations"][0]["merchant"] == "Maple Tech"
        assert payload["recommendations"][0]["has_coupon"] is True
        explanation = payload["recommendations"][0]["decision_explanation"]
        assert "Maple Tech matched wireless earbuds" in explanation["summary"]
        assert "coupon requested and available" in explanation["matched_intent"]
        assert "no model call" in explanation["guardrails"]
        assert "no web scraping" in explanation["guardrails"]
        assert [step["step"] for step in payload["evaluation_trace"]] == [
            "parse_intent",
            "retrieve_candidates",
            "rank_candidates",
        ]
        assert "no model call" in payload["evaluation_trace"][0]["notes"]
        assert "no web scraping" in payload["evaluation_trace"][1]["notes"]
        trace_event = session.get(RecommendationTraceEvent, payload["trace_event_id"])
        assert trace_event is not None
        assert trace_event.raw_intent == "Find fresh wireless earbuds with a coupon"
        assert trace_event.result_count == 1
        assert trace_event.recommended_offer_ids == [payload["recommendations"][0]["offer_id"]]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_recommendations_parse_cashback_and_popularity_intent() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)
        search_response = client.get("/search?q=buds")
        offer_ids = [result["offer_id"] for result in search_response.json()["results"]]
        client.post("/clicks", json={"offer_id": offer_ids[1], "target_type": "affiliate"})
        client.post("/clicks", json={"offer_id": offer_ids[1], "target_type": "product"})

        response = client.post(
            "/recommendations",
            json={"intent": "popular earbuds with cashback", "limit": 2},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"]["search_query"] == "earbuds"
        assert payload["intent"]["has_cashback"] is True
        assert payload["intent"]["sort"] == "clicks_desc"
        assert payload["count"] == 1
        assert payload["recommendations"][0]["offer_id"] == offer_ids[1]
        assert payload["recommendations"][0]["has_cashback"] is True
        assert "2 mock clicks" in payload["recommendations"][0]["ranking_reasons"]
        explanation = payload["recommendations"][0]["decision_explanation"]
        assert "cashback requested and available" in explanation["matched_intent"]
        assert "2 mock clicks" in explanation["ranking_signals"]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_recommendation_feedback_records_trace_offer_rating() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)
        recommendation_response = client.post(
            "/recommendations",
            json={"intent": "Find fresh wireless earbuds with a coupon", "limit": 3},
        )
        recommendation_payload = recommendation_response.json()
        offer_id = recommendation_payload["recommendations"][0]["offer_id"]
        trace_event_id = recommendation_payload["trace_event_id"]

        response = client.post(
            "/recommendations/feedback",
            json={
                "trace_event_id": trace_event_id,
                "offer_id": offer_id,
                "rating": "helpful",
                "reason": "top price and coupon fit",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["trace_event_id"] == trace_event_id
        assert payload["offer_id"] == offer_id
        assert payload["rating"] == "helpful"
        assert payload["provider_source"] == "mock_ca"
        feedback = session.get(RecommendationFeedbackEvent, payload["id"])
        assert feedback is not None
        assert feedback.reason == "top price and coupon fit"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_recommendation_feedback_rejects_offer_outside_trace() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)
        recommendation_response = client.post(
            "/recommendations",
            json={"intent": "Find fresh wireless earbuds with a coupon", "limit": 3},
        )
        trace_event_id = recommendation_response.json()["trace_event_id"]
        offer_ids = [
            result["offer_id"] for result in client.get("/search?q=kettle").json()["results"]
        ]

        response = client.post(
            "/recommendations/feedback",
            json={
                "trace_event_id": trace_event_id,
                "offer_id": offer_ids[0],
                "rating": "not_helpful",
            },
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_recommendations_validate_short_intent() -> None:
    client, session = make_client()
    try:
        response = client.post("/recommendations", json={"intent": "tv"})

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_admin_recommendation_traces_list_recent_events() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)
        recommendation_response = client.post(
            "/recommendations",
            json={"intent": "popular earbuds with cashback", "limit": 2},
        )

        response = client.get("/admin/affiliate/recommendation-traces", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_traces"] == 1
        assert payload["recent_traces"][0]["id"] == recommendation_response.json()["trace_event_id"]
        assert payload["recent_traces"][0]["strategy"] == "rule_based_mock_v0"
        assert payload["recent_traces"][0]["raw_intent"] == "popular earbuds with cashback"
        assert payload["recent_traces"][0]["parsed_intent"]["search_query"] == "earbuds"
        assert payload["recent_traces"][0]["recommended_offer_ids"]
        assert [step["step"] for step in payload["recent_traces"][0]["evaluation_trace"]] == [
            "parse_intent",
            "retrieve_candidates",
            "rank_candidates",
        ]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_admin_recommendation_evaluation_returns_fixture_summary() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        response = client.get("/admin/affiliate/recommendation-evaluation", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["strategy"] == "rule_based_mock_v0"
        assert payload["case_count"] == 4
        assert payload["passed_count"] == 4
        assert payload["failed_count"] == 0
        assert payload["cases"][0]["status"] == "pass"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_admin_recommendation_feedback_returns_summary() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        client.post("/admin/affiliate/sync/mock", headers=headers)
        recommendation_response = client.post(
            "/recommendations",
            json={"intent": "Find fresh wireless earbuds with a coupon", "limit": 3},
        )
        recommendation_payload = recommendation_response.json()
        offer_id = recommendation_payload["recommendations"][0]["offer_id"]
        trace_event_id = recommendation_payload["trace_event_id"]
        client.post(
            "/recommendations/feedback",
            json={
                "trace_event_id": trace_event_id,
                "offer_id": offer_id,
                "rating": "helpful",
            },
        )

        response = client.get("/admin/affiliate/recommendation-feedback", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_feedback"] == 1
        assert payload["helpful_count"] == 1
        assert payload["not_helpful_count"] == 0
        assert payload["recent_feedback"][0]["offer_id"] == offer_id
    finally:
        app.dependency_overrides.clear()
        session.close()
