"""Tests for the ``/admin/acquisition`` endpoints (Layer 2 advisor)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

_HDR = {"X-Admin-Token": "dev-admin-token"}


def test_requires_admin_token() -> None:
    client = TestClient(app)
    assert client.get("/admin/acquisition/data").status_code == 401
    assert client.get("/admin/acquisition/compare", params={"slug": "x"}).status_code == 401


def test_data_summary_lists_rulesets_with_disclaimer() -> None:
    client = TestClient(app)
    body = client.get("/admin/acquisition/data", headers=_HDR).json()
    assert body["programs_disclaimer"]
    prog_ids = {p["id"] for p in body["programs"]}
    assert {"outright", "carrier_financing_24", "bring_it_back_24", "apple_refurb"} <= prog_ids
    assert any(p["id"] == "big3_premium" for p in body["plans"])
    assert "smartphone_flagship" in body["depreciation_categories"]
    assert "iphone-17-pro-256gb" in body["demo_slugs"]


def test_compare_by_slug_returns_ranked_paths_and_caveats() -> None:
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
    assert len(body["ranked"]) >= 4
    costs = [t["effective_total_cents"] for t in body["ranked"]]
    assert costs == sorted(costs)
    assert body["best_label"] == body["ranked"][0]["option_label"]
    assert any("priority support" in c.lower() for c in body["caveats"])
    assert body["verify_first"]


def test_compare_by_explicit_price_and_category() -> None:
    client = TestClient(app)
    r = client.get(
        "/admin/acquisition/compare",
        params={"retail_price_cents": 120000, "category": "laptop", "brand": "apple"},
        headers=_HDR,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = {t["kind"] for t in body["ranked"]}
    assert "retail" in kinds
    assert "lease" not in kinds  # a laptop isn't carrier-eligible


def test_compare_needs_slug_or_price_plus_category() -> None:
    client = TestClient(app)
    assert client.get("/admin/acquisition/compare", headers=_HDR).status_code == 422
    assert (
        client.get("/admin/acquisition/compare", params={"slug": "nope"}, headers=_HDR).status_code
        == 404
    )
