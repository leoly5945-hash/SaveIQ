"""CP16 — public /check and /alerts (no auth, IP rate limited)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.providers import registry as registry_module
from app.providers.base import (
    ProviderCapability,
    ProviderOffer,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderPricePoint,
    ProviderProduct,
)
from app.providers.registry import ProviderRegistry
from app.services import endpoint_limit

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


class FakeKeepa:
    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset(
        {
            ProviderCapability.get_price,
            ProviderCapability.get_product,
            ProviderCapability.price_history,
            ProviderCapability.get_offers,
        }
    )

    def is_configured(self) -> bool:
        return True

    async def get_offers(self, pid: str) -> list[ProviderOffer]:
        return [
            ProviderOffer(
                provider="keepa",
                provider_product_id=pid,
                merchant="Amazon.ca",
                price_cents=4300,
                shipping_cents=0,
                currency="CAD",
                condition="new",
                is_buy_box=True,
                observed_at=NOW,
            ),
            ProviderOffer(
                provider="keepa",
                provider_product_id=pid,
                merchant="ThirdParty",
                price_cents=3999,
                shipping_cents=0,
                currency="CAD",
                condition="new",
                observed_at=NOW,
                metadata={"is_fba": True},
            ),
            ProviderOffer(
                provider="keepa",
                provider_product_id=pid,
                merchant="UsedSeller",
                price_cents=3400,
                shipping_cents=0,
                currency="CAD",
                condition="used",
                observed_at=NOW,
            ),
        ]

    async def get_product(self, pid: str) -> ProviderProduct | None:
        return ProviderProduct(
            provider="keepa",
            provider_product_id=pid,
            title="Anker 737 Power Bank",
            market="CA",
            currency="CAD",
            product_url=f"https://www.amazon.ca/dp/{pid}",
        )

    async def get_price(self, pid: str) -> ProviderPrice | None:
        return ProviderPrice(
            provider="keepa",
            provider_product_id=pid,
            price_cents=4300,
            currency="CAD",
            observed_at=NOW,
            source="keepa:buy_box",
        )

    async def get_price_history(self, pid: str, *, days: int = 180) -> ProviderPriceHistory | None:
        pts = [
            ProviderPricePoint(
                observed_at=NOW - timedelta(days=d), price_cents=5000 - (d % 3) * 40, kind="buy_box"
            )
            for d in range(0, 90)
        ]
        return ProviderPriceHistory(
            provider="keepa",
            provider_product_id=pid,
            currency="CAD",
            points=pts,
            metadata={"base_kind": "buy_box", "keepa_stats": {"avg90_cents": 4600}},
        )


def _dfs_offers(provider_product_id: str) -> list[ProviderOffer]:
    return [
        ProviderOffer(
            provider="dataforseo",
            provider_product_id=provider_product_id,
            merchant="Walmart Canada",
            price_cents=3999,
            currency="CAD",
            url="https://www.walmart.ca/en/ip/anker-737/1",
            observed_at=NOW,
            metadata={"title": "Anker 737 Power Bank PowerCore 24K"},
        ),
        ProviderOffer(
            provider="dataforseo",
            provider_product_id=provider_product_id,
            merchant="Best Buy Canada",
            price_cents=4599,
            currency="CAD",
            url="https://www.bestbuy.ca/anker-737",
            observed_at=NOW,
            metadata={"title": "Anker 737 Power Bank"},
        ),
    ]


class FakeDataForSEO:
    """Task-based DataForSEO stub: submit returns a task id, fetch returns offers."""

    name = "dataforseo"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset(
        {ProviderCapability.search, ProviderCapability.get_offers, ProviderCapability.get_price}
    )

    def __init__(self, *, ready: bool = True) -> None:
        self._ready = ready
        self.submitted: list[str] = []

    def is_configured(self) -> bool:
        return True

    async def submit_offers_task(self, keyword: str) -> str:
        self.submitted.append(keyword)
        return "task-abc"

    async def fetch_offers_task(
        self, task_id: str, *, provider_product_id: str | None = None
    ) -> list[ProviderOffer] | None:
        if not self._ready:
            return None
        return _dfs_offers(provider_product_id or "ref")

    async def get_offers(self, provider_product_id: str) -> list[ProviderOffer]:
        return _dfs_offers(provider_product_id)

    async def get_price(self, provider_product_id: str):  # pragma: no cover
        return None

    async def search_products(self, query: str, *, limit: int = 10):  # pragma: no cover
        return []

    async def get_price_history(self, provider_product_id: str, *, days: int = 180):
        return None


def _seed_ready_comparison(session: Session, pid: str) -> None:
    from app.models.comparison import ComparisonStatus, MerchantComparison

    session.add(
        MerchantComparison(
            provider="keepa",
            provider_product_id=pid,
            market="CA",
            status=ComparisonStatus.ready.value,
            keyword="Anker 737 Power Bank",
            task_id="task-abc",
            currency="CAD",
            offers_json=[
                {
                    "merchant": "Walmart Canada",
                    "price_cents": 3999,
                    "shipping_cents": 0,
                    "currency": "CAD",
                    "url": "https://www.walmart.ca/en/ip/anker-737/1",
                    "title": "Anker 737 Power Bank PowerCore 24K",
                },
                {
                    "merchant": "Best Buy Canada",
                    "price_cents": 4599,
                    "shipping_cents": 0,
                    "currency": "CAD",
                    "url": "https://www.bestbuy.ca/anker-737",
                    "title": "Anker 737 Power Bank",
                },
            ],
            requested_at=datetime.now(UTC) - timedelta(minutes=5),
            completed_at=datetime.now(UTC) - timedelta(minutes=5),
            expires_at=datetime.now(UTC) + timedelta(hours=23),
        )
    )
    session.commit()


def _client(monkeypatch, *providers: object) -> tuple[TestClient, Session]:
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
    reg = ProviderRegistry()
    for provider in providers or (FakeKeepa(),):
        reg.register(provider)
    monkeypatch.setattr(registry_module, "_default_registry", reg)
    endpoint_limit.reset_for_tests()
    return TestClient(app), session


def test_public_check_from_url(monkeypatch) -> None:
    client, session = _client(monkeypatch)
    try:
        resp = client.get(
            "/check", params={"url": "https://www.amazon.ca/Anker-737/dp/B09VPHVT9Z/ref=x"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["provider"] == "keepa"
        assert body["provider_product_id"] == "B09VPHVT9Z"
        assert body["title"] == "Anker 737 Power Bank"
        assert body["assessment"]["verdict"] in {"BUY", "FAIR", "WAIT", "UNKNOWN"}
        assert body["assessment"]["reasons"]
        assert body["currency"] == "CAD"
        spark = body["sparkline"]
        assert 2 <= len(spark) <= 60
        assert all(set(p) == {"t", "c"} and isinstance(p["c"], int) for p in spark)
        assert spark == sorted(spark, key=lambda p: p["t"])
        assert body["comparison"] is None  # no dataforseo provider registered
        # the Amazon offer spread comes from the (fake) Keepa get_offers
        spread = body["spread"]
        assert spread is not None
        assert spread["buy_box_cents"] == 4300
        conditions = {t["condition"] for t in spread["tiers"]}
        assert conditions == {"new", "used"}
        assert spread["lowest_overall_cents"] == 3400
        assert spread["savings_vs_buy_box_cents"] == 900
        new_tier = next(t for t in spread["tiers"] if t["condition"] == "new")
        assert new_tier["lowest_total_cents"] == 3999 and new_tier["fba_available"] is True
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_public_check_renders_cached_comparison(monkeypatch) -> None:
    client, session = _client(monkeypatch, FakeKeepa(), FakeDataForSEO())
    try:
        _seed_ready_comparison(session, "B09VPHVT9Z")
        resp = client.get("/check", params={"product_id": "B09VPHVT9Z"})
        assert resp.status_code == 200, resp.text
        comp = resp.json()["comparison"]
        assert comp is not None
        assert comp["reference_merchant"] == "Amazon.ca"
        # Keepa's effective price is 43.00 — Walmart's 39.99 beats it; Best Buy's
        # 45.99 is above the reference and is not shown.
        merchants = [o["merchant"] for o in comp["offers"]]
        assert merchants == ["Walmart Canada"]
        assert comp["offers"][0]["price_cents"] == 3999
        assert comp["cheapest"]["merchant"] == "Walmart Canada"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_public_check_primes_comparison_task_when_cold(monkeypatch) -> None:
    from app.models.comparison import ComparisonStatus, MerchantComparison

    dfs = FakeDataForSEO()
    client, session = _client(monkeypatch, FakeKeepa(), dfs)
    try:
        resp = client.get("/check", params={"product_id": "B09VPHVT9Z"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["comparison"] is None  # first check: nothing cached yet
        assert dfs.submitted == ["Anker 737 Power Bank"]  # a task was posted
        row = session.query(MerchantComparison).one()
        assert row.status == ComparisonStatus.pending.value
        assert row.task_id == "task-abc"
        assert row.provider_product_id == "B09VPHVT9Z"
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_public_check_survives_comparison_provider_failure(monkeypatch) -> None:
    class BrokenDFS(FakeDataForSEO):
        async def submit_offers_task(self, keyword: str) -> str:
            raise RuntimeError("dataforseo is down")

    client, session = _client(monkeypatch, FakeKeepa(), BrokenDFS())
    try:
        resp = client.get("/check", params={"product_id": "B09VPHVT9Z"})
        assert resp.status_code == 200  # the verdict still works
        assert resp.json()["comparison"] is None
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_public_check_rejects_non_ca(monkeypatch) -> None:
    client, session = _client(monkeypatch)
    try:
        resp = client.get("/check", params={"url": "https://www.amazon.com/dp/B09VPHVT9Z"})
        assert resp.status_code == 422
        assert "Amazon.ca" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_public_check_needs_input(monkeypatch) -> None:
    client, session = _client(monkeypatch)
    try:
        assert client.get("/check").status_code == 422
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_endpoint_limit_allows_then_blocks(monkeypatch) -> None:
    from app.core import settings as settings_module

    class _S:
        rate_limit_enabled = True
        redis_url = "redis://localhost:6379/0"

    monkeypatch.setattr(settings_module, "get_settings", lambda: _S())
    monkeypatch.setattr(endpoint_limit, "get_settings", lambda: _S())
    endpoint_limit.reset_for_tests()

    assert endpoint_limit.allow("t", "1.2.3.4", per_minute=2) is True
    assert endpoint_limit.allow("t", "1.2.3.4", per_minute=2) is True
    assert endpoint_limit.allow("t", "1.2.3.4", per_minute=2) is False
    # A different identity has its own window.
    assert endpoint_limit.allow("t", "9.9.9.9", per_minute=2) is True


def test_endpoint_limit_off_when_disabled(monkeypatch) -> None:
    class _S:
        rate_limit_enabled = False
        redis_url = "redis://localhost:6379/0"

    monkeypatch.setattr(endpoint_limit, "get_settings", lambda: _S())
    endpoint_limit.reset_for_tests()
    for _ in range(50):
        assert endpoint_limit.allow("t", "1.2.3.4", per_minute=1) is True


def test_public_create_alert_and_unsubscribe(monkeypatch) -> None:
    client, session = _client(monkeypatch)
    try:
        created = client.post(
            "/alerts",
            json={
                "email": "shopper@example.com",
                "url": "https://www.amazon.ca/dp/B09VPHVT9Z",
                "kind": "any_drop",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["baseline_cents"] == 4300
        assert body["provider_product_id"] == "B09VPHVT9Z"
        token = body["unsubscribe_url"].split("token=")[1]

        r = client.get("/alerts/unsubscribe", params={"token": token})
        assert r.status_code == 200 and r.json()["ok"] is True
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_public_create_alert_rejects_bad_email(monkeypatch) -> None:
    client, session = _client(monkeypatch)
    try:
        resp = client.post(
            "/alerts",
            json={"email": "nope", "product_id": "B09VPHVT9Z"},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
        session.close()


@pytest.mark.parametrize("route", ["/check", "/alerts"])
def test_public_routes_are_unauthenticated(monkeypatch, route: str) -> None:
    # No X-Admin-Token header at all — must not 401.
    client, session = _client(monkeypatch)
    try:
        if route == "/check":
            code = client.get(route, params={"product_id": "B09VPHVT9Z"}).status_code
        else:
            code = client.post(
                route, json={"email": "a@b.co", "product_id": "B09VPHVT9Z"}
            ).status_code
        assert code != 401
    finally:
        app.dependency_overrides.clear()
        session.close()
