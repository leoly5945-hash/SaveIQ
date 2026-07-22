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


def test_admin_endpoints_require_authorization() -> None:
    client, session = make_client()
    try:
        response = client.get("/admin/affiliate/products")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_run_mock_sync_and_view_admin_resources() -> None:
    client, session = make_client()
    headers = {"X-Admin-Token": "dev-admin-token"}
    try:
        sync_response = client.post("/admin/affiliate/sync/mock", headers=headers)
        products_response = client.get("/admin/affiliate/products", headers=headers)
        offers_response = client.get("/admin/affiliate/offers", headers=headers)
        errors_response = client.get("/admin/affiliate/sync/errors", headers=headers)
        summary_response = client.get("/admin/affiliate/staging-summary", headers=headers)

        assert sync_response.status_code == 200
        assert sync_response.json()["stats"]["received"] == 12
        assert products_response.status_code == 200
        assert len(products_response.json()) == 5
        assert offers_response.status_code == 200
        assert len(offers_response.json()) == 6
        assert errors_response.status_code == 200
        assert errors_response.json()[0]["error_code"] == "malformed_record"
        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["counts"]["products"] == 5
        assert summary["counts"]["offers"] == 6
        assert summary["counts"]["sync_errors"] == 1
        assert summary["latest_sync_job"]["provider_source"] == "mock_ca"
        assert summary["latest_sync_job"]["received_count"] == 12
        assert summary["recent_errors"][0]["error_code"] == "malformed_record"
    finally:
        app.dependency_overrides.clear()
        session.close()
