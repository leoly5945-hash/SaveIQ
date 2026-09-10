"""Tests for the ``/admin/acquisition`` endpoints (Layer 2 advisor)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

_HDR = {"X-Admin-Token": "dev-admin-token"}


def test_requires_admin_token() -> None:
    client = TestClient(app)
    assert client.get("/admin/acquisition/catalog").status_code == 401
    assert client.get("/admin/acquisition/compare", params={"slug": "x"}).status_code == 401


def test_catalog_lists_seeded_products_with_disclaimer() -> None:
    client = TestClient(app)
    body = client.get("/admin/acquisition/catalog", headers=_HDR).json()
    assert body["disclaimer"]
    slugs = {p["slug"] for p in body["products"]}
    assert "iphone-17-pro-256gb" in slugs
    entry = next(p for p in body["products"] if p["slug"] == "iphone-17-pro-256gb")
    assert entry["option_count"] == 4


def test_compare_unknown_slug_is_404() -> None:
    client = TestClient(app)
    r = client.get("/admin/acquisition/compare", params={"slug": "nope"}, headers=_HDR)
    assert r.status_code == 404


def test_compare_returns_ranked_paths_and_profile_caveats() -> None:
    client = TestClient(app)
    r = client.get(
        "/admin/acquisition/compare",
        params={
            "slug": "iphone-17-pro-256gb",
            "horizon_months": 36,
            "annual_discount_rate": 0.06,
            "is_business": True,
            "service_sensitivity": "high",
        },
        headers=_HDR,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_slug"] == "iphone-17-pro-256gb"
    assert len(body["ranked"]) == 4
    costs = [t["effective_total_cents"] for t in body["ranked"]]
    assert costs == sorted(costs)
    assert body["best_label"] == body["ranked"][0]["option_label"]
    assert any("priority support" in c.lower() for c in body["caveats"])
    assert body["verify_first"]
