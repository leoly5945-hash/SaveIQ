"""Gate 8 personalization / anonymous user profile tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.bandit.features import FEATURE_NAMES, BanditContext, build_feature_vector
from app.services.user.embedding import EMBEDDING_DIM, compute_user_embedding
from app.services.user.identity import normalize_anonymous_user_id
from app.services.user.profile import UserProfileService
from app.services.user.rerank import apply_personalization_boost


def test_anonymous_user_id_rejects_pii() -> None:
    assert normalize_anonymous_user_id("anon_user_01") == "anon_user_01"
    with pytest.raises(ValueError):
        normalize_anonymous_user_id("user@example.com")
    with pytest.raises(ValueError):
        normalize_anonymous_user_id("1234567890")


def test_embedding_is_fixed_dim_and_normalized() -> None:
    vector = compute_user_embedding(
        click_history=[1, 2, 3],
        preferred_categories=["grocery", "dairy"],
    )
    assert len(vector) == EMBEDDING_DIM
    norm = sum(value * value for value in vector) ** 0.5
    assert 0.99 <= norm <= 1.01


def test_bandit_features_include_personalization_slots() -> None:
    vector = build_feature_vector(BanditContext(query_text="milk"))
    assert len(vector) == len(FEATURE_NAMES)
    assert "emb_0" in FEATURE_NAMES
    assert "session_count_norm" in FEATURE_NAMES


def test_rerank_boosts_preferred_category() -> None:
    from datetime import UTC, datetime

    from app.services.user.profile import UserProfile

    profile = UserProfile(
        user_id="anon_user_01",
        preferred_categories=["dairy"],
        avg_query_length=10.0,
        click_history=[1],
        session_count=2,
        total_clicks=1,
        total_feedback=0,
        last_active=datetime.now(UTC),
        personalization_opt_out=False,
        embedding=[0.0] * EMBEDDING_DIM,
        personalization_active=True,
    )
    results = [
        {
            "offer_id": 1,
            "category": "snacks",
            "decision_explanation": {
                "summary": "a",
                "matched_intent": [],
                "ranking_signals": [],
                "guardrails": [],
            },
        },
        {
            "offer_id": 2,
            "category": "dairy",
            "decision_explanation": {
                "summary": "b",
                "matched_intent": [],
                "ranking_signals": [],
                "guardrails": [],
            },
        },
    ]
    boosted = apply_personalization_boost(results, profile)
    assert boosted[0]["offer_id"] == 2


def test_personalization_api_and_stats() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_settings() -> Settings:
        return Settings(
            FEATURE_PERSONALIZATION="true",
            ADMIN_API_TOKEN="dev-admin-token",
            PERSONALIZATION_CACHE_ENABLED="false",
        )

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = override_settings
    client = TestClient(app)
    headers = {"X-Anonymous-User-Id": "smoke_user_01"}

    status = client.get("/personalization/status")
    assert status.status_code == 200
    assert status.json()["feature_enabled"] is True
    assert status.json()["pii_policy"] == "anonymous_opaque_ids_only"

    profile = client.get("/user/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["user_id"] == "smoke_user_01"
    assert profile.json()["personalization_opt_out"] is False

    feedback = client.post(
        "/user/feedback",
        headers=headers,
        json={"offer_id": 42, "action": "click", "category": "dairy"},
    )
    assert feedback.status_code == 201
    assert feedback.json()["accepted"] is True
    assert "dairy" in feedback.json()["profile"]["preferred_categories"]

    opt_out = client.post("/user/opt-out", headers=headers, json={"opt_out": True})
    assert opt_out.status_code == 200
    assert opt_out.json()["personalization_opt_out"] is True
    assert opt_out.json()["personalization_active"] is False

    stats = client.get(
        "/admin/users/stats",
        headers={"X-Admin-Token": "dev-admin-token"},
    )
    assert stats.status_code == 200
    assert stats.json()["user_count"] >= 1
    assert stats.json()["opt_out_count"] >= 1


def test_profile_service_disabled_skips_events() -> None:
    settings = Settings(FEATURE_PERSONALIZATION="false")
    service = UserProfileService(settings)
    assert service.enabled() is False
    assert service.record_event("anon_user_01", event_type="click", offer_id=1) is None


def test_settings_personalization_default_off() -> None:
    settings = Settings()
    assert settings.feature_personalization is False
