from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_integrations_status_reports_states_not_secrets() -> None:
    client = TestClient(app)
    response = client.get("/health/integrations")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"amazon_images", "ebay_offers", "store_links"}
    assert body["amazon_images"] == "not_configured"
    assert body["ebay_offers"] == "not_configured"
    assert body["store_links"] == "not_configured"
