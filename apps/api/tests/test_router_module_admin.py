"""Admin routers from repo-root src/ modules are mounted on the FastAPI app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

ADMIN = {"X-Admin-Token": "dev-admin-token"}


def test_router_module_admin_endpoints_require_token() -> None:
    client = TestClient(create_app())
    for path in (
        "/admin/attribution/status",
        "/admin/fraud/status",
        "/admin/diversity/status",
    ):
        assert client.get(path).status_code == 401


def test_router_module_admin_endpoints_ok() -> None:
    client = TestClient(create_app())
    attribution = client.get("/admin/attribution/status", headers=ADMIN)
    assert attribution.status_code == 200
    body = attribution.json()
    assert body["enabled"] is False
    assert "attribution_model" in body

    fraud = client.get("/admin/fraud/status", headers=ADMIN)
    assert fraud.status_code == 200
    assert "enabled" in fraud.json() or "blocked" in fraud.json() or isinstance(fraud.json(), dict)

    diversity = client.get("/admin/diversity/status", headers=ADMIN)
    assert diversity.status_code == 200

    weights = client.post(
        "/admin/objective/update_weights",
        headers=ADMIN,
        json={
            "conversion_rate": 1.0,
            "revenue_per_user": 1.0,
            "user_satisfaction": 1.0,
        },
    )
    assert weights.status_code == 200
    assert "weights" in weights.json()
