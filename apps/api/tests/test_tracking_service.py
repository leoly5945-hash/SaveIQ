"""Tests for CP15 tracking + price-alert service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.tracking import AlertKind, AlertStatus, PriceAlert
from app.providers.base import (
    ProviderCapability,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderProduct,
)
from app.providers.registry import ProviderRegistry
from app.services.tracking.email import EmailMessage
from app.services.tracking.service import (
    TrackingError,
    create_alert,
    evaluate_alert,
    get_or_create_tracked_product,
    latest_observation,
    record_observation,
    run_alert_cycle,
    unsubscribe,
)

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


class CollectingEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class FakeKeepa:
    name = "keepa"
    market = "CA"
    currency = "CAD"
    capabilities = frozenset({ProviderCapability.get_price, ProviderCapability.price_history})

    def __init__(self, price_cents: int, avg90_cents: int | None = 5000) -> None:
        self._price = price_cents
        self._avg90 = avg90_cents

    def is_configured(self) -> bool:
        return True

    async def get_product(self, pid: str) -> ProviderProduct | None:
        return ProviderProduct(
            provider="keepa", provider_product_id=pid, title="Widget", market="CA", currency="CAD"
        )

    async def get_price(self, pid: str) -> ProviderPrice | None:
        return ProviderPrice(
            provider="keepa",
            provider_product_id=pid,
            price_cents=self._price,
            currency="CAD",
            observed_at=NOW,
            source="keepa:buy_box",
        )

    async def get_price_history(self, pid: str, *, days: int = 180) -> ProviderPriceHistory | None:
        return ProviderPriceHistory(
            provider="keepa",
            provider_product_id=pid,
            currency="CAD",
            points=[],
            metadata={"keepa_stats": {"avg90_cents": self._avg90}},
        )


def _tracked(db: Session, **kw):
    return get_or_create_tracked_product(
        db,
        provider="keepa",
        provider_product_id=kw.get("asin", "B0000TEST1"),
        market="CA",
        title=kw.get("title", "Widget"),
    )


def test_get_or_create_is_idempotent(db_session: Session) -> None:
    a = _tracked(db_session)
    b = _tracked(db_session)
    assert a.id == b.id
    assert a.title == "Widget"


def test_record_observation_dedupes_on_timestamp(db_session: Session) -> None:
    tracked = _tracked(db_session)
    o1 = record_observation(
        db_session,
        tracked,
        effective_price_cents=1000,
        currency="CAD",
        source="keepa:buy_box",
        observed_at=NOW,
    )
    o2 = record_observation(
        db_session,
        tracked,
        effective_price_cents=1200,
        currency="CAD",
        source="keepa:buy_box",
        observed_at=NOW,
    )
    assert o1.id == o2.id
    assert latest_observation(db_session, tracked).effective_price_cents == 1000


def test_create_alert_sets_baseline_from_latest_observation(db_session: Session) -> None:
    tracked = _tracked(db_session)
    record_observation(
        db_session,
        tracked,
        effective_price_cents=4200,
        currency="CAD",
        source="keepa:buy_box",
        observed_at=NOW,
    )
    alert = create_alert(db_session, tracked, email="Me@Example.com", kind=AlertKind.any_drop)
    assert alert.baseline_cents == 4200
    assert alert.email == "me@example.com"  # normalised
    assert alert.status == AlertStatus.active.value
    assert len(alert.unsubscribe_token) >= 32


def test_create_alert_below_requires_threshold(db_session: Session) -> None:
    tracked = _tracked(db_session)
    with pytest.raises(TrackingError):
        create_alert(db_session, tracked, email="a@b.co", kind=AlertKind.below)


def test_create_alert_rejects_bad_email(db_session: Session) -> None:
    tracked = _tracked(db_session)
    with pytest.raises(TrackingError):
        create_alert(db_session, tracked, email="not-an-email", kind=AlertKind.any_drop)


def _mk_alert(db_session, kind, *, baseline=None, threshold=None) -> PriceAlert:
    tracked = _tracked(db_session)
    alert = PriceAlert(
        tracked_product_id=tracked.id,
        email="a@b.co",
        kind=kind.value,
        threshold_cents=threshold,
        baseline_cents=baseline,
        status=AlertStatus.active.value,
        unsubscribe_token=f"tok-{kind.value}",
    )
    db_session.add(alert)
    db_session.flush()
    return alert


def test_evaluate_any_drop(db_session: Session) -> None:
    alert = _mk_alert(db_session, AlertKind.any_drop, baseline=5000)
    obs = record_observation(
        db_session,
        alert.tracked_product,
        effective_price_cents=4700,
        currency="CAD",
        source="s",
        observed_at=NOW,
    )
    trig = evaluate_alert(alert, obs, min_drop_pct=1.0)
    assert trig is not None and "dropped 6%" in trig.reason
    # Not enough of a drop.
    obs2 = record_observation(
        db_session,
        alert.tracked_product,
        effective_price_cents=4990,
        currency="CAD",
        source="s",
        observed_at=NOW + timedelta(days=1),
    )
    assert evaluate_alert(alert, obs2, min_drop_pct=1.0) is None


def test_evaluate_below_threshold(db_session: Session) -> None:
    alert = _mk_alert(db_session, AlertKind.below, threshold=4000)
    below = record_observation(
        db_session,
        alert.tracked_product,
        effective_price_cents=3999,
        currency="CAD",
        source="s",
        observed_at=NOW,
    )
    assert evaluate_alert(alert, below, min_drop_pct=1.0) is not None
    above = record_observation(
        db_session,
        alert.tracked_product,
        effective_price_cents=4001,
        currency="CAD",
        source="s",
        observed_at=NOW + timedelta(days=1),
    )
    assert evaluate_alert(alert, above, min_drop_pct=1.0) is None


def test_evaluate_at_or_below_average(db_session: Session) -> None:
    alert = _mk_alert(db_session, AlertKind.at_or_below_average)
    obs = record_observation(
        db_session,
        alert.tracked_product,
        effective_price_cents=4500,
        currency="CAD",
        source="s",
        avg90_cents=4600,
        observed_at=NOW,
    )
    assert evaluate_alert(alert, obs, min_drop_pct=1.0) is not None


def test_unsubscribe(db_session: Session) -> None:
    alert = _mk_alert(db_session, AlertKind.any_drop, baseline=5000)
    assert unsubscribe(db_session, alert.unsubscribe_token) is True
    db_session.refresh(alert)
    assert alert.status == AlertStatus.unsubscribed.value
    assert unsubscribe(db_session, "nope-nope-nope-nope") is False


@pytest.mark.asyncio
async def test_run_alert_cycle_fires_and_emails_once(db_session: Session) -> None:
    registry = ProviderRegistry()
    registry.register(FakeKeepa(price_cents=4700))  # dropped from a 5000 baseline

    tracked = get_or_create_tracked_product(
        db_session, provider="keepa", provider_product_id="B0000TEST1", market="CA", title="Widget"
    )
    record_observation(
        db_session,
        tracked,
        effective_price_cents=5000,
        currency="CAD",
        source="keepa:buy_box",
        observed_at=NOW - timedelta(days=1),
    )
    alert = create_alert(db_session, tracked, email="a@b.co", kind=AlertKind.any_drop)
    assert alert.baseline_cents == 5000

    sender = CollectingEmailSender()
    stats = await run_alert_cycle(db_session, registry, email_sender=sender, now=NOW)

    assert stats.tracked_checked == 1
    assert stats.observations_recorded == 1
    assert stats.alerts_fired == 1
    assert stats.emails_sent == 1
    assert len(sender.sent) == 1
    assert "dropped" in sender.sent[0].text_body
    assert "amazon.ca/dp/B0000TEST1" in sender.sent[0].text_body

    db_session.refresh(alert)
    assert alert.status == AlertStatus.fired.value
    assert alert.notify_count == 1

    # Second cycle: same price, alert already fired -> no new email.
    stats2 = await run_alert_cycle(
        db_session, registry, email_sender=sender, now=NOW + timedelta(days=1)
    )
    assert stats2.alerts_fired == 0
    assert len(sender.sent) == 1


@pytest.mark.asyncio
async def test_run_alert_cycle_no_fire_when_price_holds(db_session: Session) -> None:
    registry = ProviderRegistry()
    registry.register(FakeKeepa(price_cents=5000))
    tracked = get_or_create_tracked_product(
        db_session, provider="keepa", provider_product_id="B0000HOLD1", market="CA", title="Widget"
    )
    record_observation(
        db_session,
        tracked,
        effective_price_cents=5000,
        currency="CAD",
        source="keepa:buy_box",
        observed_at=NOW - timedelta(days=1),
    )
    create_alert(db_session, tracked, email="a@b.co", kind=AlertKind.any_drop)

    sender = CollectingEmailSender()
    stats = await run_alert_cycle(db_session, registry, email_sender=sender, now=NOW)
    assert stats.alerts_fired == 0
    assert sender.sent == []
