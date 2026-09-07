"""CP15 — tracked products, price observations, and price-alert evaluation."""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.models.tracking import (
    AlertKind,
    AlertStatus,
    PriceAlert,
    PriceObservation,
    TrackedProduct,
)
from app.providers import ProviderError
from app.providers.registry import ProviderRegistry
from app.services.decision.assess import assess_from_provider
from app.services.decision.price_check import PriceCheckError, resolve_target
from app.services.tracking.email import EmailMessage, EmailSender

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class TrackingError(RuntimeError):
    """A tracking operation could not be completed."""


@dataclass(frozen=True)
class AlertTrigger:
    alert_id: int
    email: str
    reason: str
    price_cents: int
    currency: str


@dataclass
class CycleStats:
    tracked_checked: int = 0
    observations_recorded: int = 0
    alerts_evaluated: int = 0
    alerts_fired: int = 0
    emails_sent: int = 0
    errors: int = 0


def _now() -> datetime:
    return datetime.now(tz=UTC)


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise TrackingError("invalid email address")
    return email


def amazon_affiliate_url(asin: str, *, market: str, tag: str) -> str:
    host = {
        "CA": "www.amazon.ca",
        "US": "www.amazon.com",
        "GB": "www.amazon.co.uk",
    }.get(market, "www.amazon.ca")
    return f"https://{host}/dp/{asin}?tag={tag}"


# -- tracked products -------------------------------------------------------


def get_or_create_tracked_product(
    db: Session,
    *,
    provider: str,
    provider_product_id: str,
    market: str,
    title: str | None = None,
    product_url: str | None = None,
) -> TrackedProduct:
    provider_product_id = provider_product_id.strip().upper()
    market = market.strip().upper()
    existing = db.execute(
        select(TrackedProduct).where(
            TrackedProduct.provider == provider,
            TrackedProduct.provider_product_id == provider_product_id,
            TrackedProduct.market == market,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if title and not existing.title:
            existing.title = title
        if product_url and not existing.product_url:
            existing.product_url = product_url
        return existing

    tracked = TrackedProduct(
        provider=provider,
        provider_product_id=provider_product_id,
        market=market,
        title=title,
        product_url=product_url,
    )
    db.add(tracked)
    db.flush()
    return tracked


def record_observation(
    db: Session,
    tracked: TrackedProduct,
    *,
    effective_price_cents: int,
    currency: str,
    source: str,
    avg90_cents: int | None = None,
    verdict: str | None = None,
    score: int | None = None,
    observed_at: datetime | None = None,
) -> PriceObservation:
    observed_at = observed_at or _now()
    existing = db.execute(
        select(PriceObservation).where(
            PriceObservation.tracked_product_id == tracked.id,
            PriceObservation.observed_at == observed_at,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    observation = PriceObservation(
        tracked_product_id=tracked.id,
        observed_at=observed_at,
        effective_price_cents=effective_price_cents,
        currency=currency,
        source=source,
        avg90_cents=avg90_cents,
        verdict=verdict,
        score=score,
    )
    db.add(observation)
    tracked.last_checked_at = observed_at
    db.flush()
    return observation


def latest_observation(db: Session, tracked: TrackedProduct) -> PriceObservation | None:
    return db.execute(
        select(PriceObservation)
        .where(PriceObservation.tracked_product_id == tracked.id)
        .order_by(PriceObservation.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


# -- alerts ---------------------------------------------------------------


def create_alert(
    db: Session,
    tracked: TrackedProduct,
    *,
    email: str,
    kind: AlertKind,
    threshold_cents: int | None = None,
) -> PriceAlert:
    email = normalize_email(email)
    if kind == AlertKind.below and (threshold_cents is None or threshold_cents <= 0):
        raise TrackingError("threshold_cents is required for a 'below' alert")

    latest = latest_observation(db, tracked)
    baseline = latest.effective_price_cents if latest is not None else None

    alert = PriceAlert(
        tracked_product_id=tracked.id,
        email=email,
        kind=kind.value,
        threshold_cents=threshold_cents if kind == AlertKind.below else None,
        baseline_cents=baseline,
        status=AlertStatus.active.value,
        unsubscribe_token=secrets.token_urlsafe(32),
    )
    db.add(alert)
    db.flush()
    return alert


async def track_and_alert(
    db: Session,
    registry: ProviderRegistry,
    *,
    email: str,
    kind: AlertKind,
    threshold_cents: int | None = None,
    product_id: str | None = None,
    url: str | None = None,
) -> tuple[PriceAlert, TrackedProduct]:
    """Full flow: (URL | id) -> provider -> tracked product + one observation +
    a new alert. Raises :class:`PriceCheckError` (status + detail) on any gate.
    """

    resolved_id, hint = resolve_target(product_id, url)
    adapter = registry.try_get(hint or "keepa") or registry.try_get("keepa")
    if adapter is None:
        raise PriceCheckError(503, "no keepa provider configured")

    try:
        product = await adapter.get_product(resolved_id)
        price = await adapter.get_price(resolved_id)
        history = await adapter.get_price_history(resolved_id, days=90)
    except ProviderError as exc:
        raise PriceCheckError(502, f"provider error: {exc}") from exc

    tracked = get_or_create_tracked_product(
        db,
        provider=adapter.name,
        provider_product_id=resolved_id,
        market=adapter.market,
        title=product.title if product else None,
        product_url=product.product_url if product else None,
    )

    if price is not None and price.price_cents is not None and history is not None:
        assessment = assess_from_provider(price, history)
        avg90 = verdict = score = None
        if assessment is not None:
            avg90 = (assessment.intelligence.provider_stats or {}).get("avg90_cents")
            verdict = assessment.verdict.value
            score = assessment.score
        record_observation(
            db,
            tracked,
            effective_price_cents=price.price_cents,
            currency=price.currency,
            source=price.source,
            avg90_cents=avg90,
            verdict=verdict,
            score=score,
        )

    try:
        alert = create_alert(db, tracked, email=email, kind=kind, threshold_cents=threshold_cents)
    except TrackingError as exc:
        raise PriceCheckError(422, str(exc)) from exc
    return alert, tracked


def unsubscribe(db: Session, token: str) -> bool:
    alert = db.execute(
        select(PriceAlert).where(PriceAlert.unsubscribe_token == token)
    ).scalar_one_or_none()
    if alert is None:
        return False
    if alert.status != AlertStatus.unsubscribed.value:
        alert.status = AlertStatus.unsubscribed.value
        db.flush()
    return True


def evaluate_alert(
    alert: PriceAlert,
    observation: PriceObservation,
    *,
    min_drop_pct: float,
) -> AlertTrigger | None:
    """Deterministic: does ``observation`` trip ``alert``? Pure, no I/O."""

    if alert.status != AlertStatus.active.value:
        return None
    price = observation.effective_price_cents
    currency = observation.currency

    if alert.kind == AlertKind.below.value:
        if alert.threshold_cents is not None and price <= alert.threshold_cents:
            return AlertTrigger(
                alert_id=alert.id,
                email=alert.email,
                reason=f"now {_money(price, currency)} — at or below your "
                f"{_money(alert.threshold_cents, currency)} target",
                price_cents=price,
                currency=currency,
            )
        return None

    if alert.kind == AlertKind.at_or_below_average.value:
        avg = observation.avg90_cents
        if avg is not None and avg > 0 and price <= avg:
            return AlertTrigger(
                alert_id=alert.id,
                email=alert.email,
                reason=f"now {_money(price, currency)} — at or below the "
                f"90-day average of {_money(avg, currency)}",
                price_cents=price,
                currency=currency,
            )
        return None

    # any_drop
    base = alert.baseline_cents
    if base is not None and base > 0:
        drop_pct = (base - price) / base * 100.0
        if drop_pct >= min_drop_pct:
            return AlertTrigger(
                alert_id=alert.id,
                email=alert.email,
                reason=f"dropped {drop_pct:.0f}% — from {_money(base, currency)} "
                f"to {_money(price, currency)}",
                price_cents=price,
                currency=currency,
            )
    return None


# -- the daily cycle ----------------------------------------------------


async def run_alert_cycle(
    db: Session,
    registry: ProviderRegistry,
    *,
    email_sender: EmailSender,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> CycleStats:
    """Re-check every tracked product, record an observation, fire due alerts."""

    settings = settings or get_settings()
    now = now or _now()
    stats = CycleStats()

    tracked_products = list(db.execute(select(TrackedProduct)).scalars())
    for tracked in tracked_products:
        stats.tracked_checked += 1
        adapter = registry.try_get(tracked.provider)
        if adapter is None:
            stats.errors += 1
            logger.warning("no provider for tracked product", extra={"provider": tracked.provider})
            continue
        try:
            price = await adapter.get_price(tracked.provider_product_id)
            history = await adapter.get_price_history(tracked.provider_product_id, days=90)
        except Exception:  # noqa: BLE001 - one bad product must not stop the cycle
            stats.errors += 1
            logger.exception("price fetch failed", extra={"asin": tracked.provider_product_id})
            continue
        if price is None or price.price_cents is None or history is None:
            continue

        assessment = assess_from_provider(price, history, now=now)
        avg90 = None
        verdict = None
        score = None
        if assessment is not None:
            avg90 = (assessment.intelligence.provider_stats or {}).get("avg90_cents")
            verdict = assessment.verdict.value
            score = assessment.score

        observation = record_observation(
            db,
            tracked,
            effective_price_cents=price.price_cents,
            currency=price.currency,
            source=price.source,
            avg90_cents=avg90,
            verdict=verdict,
            score=score,
            observed_at=now,
        )
        stats.observations_recorded += 1

        active_alerts = list(
            db.execute(
                select(PriceAlert).where(
                    PriceAlert.tracked_product_id == tracked.id,
                    PriceAlert.status == AlertStatus.active.value,
                )
            ).scalars()
        )
        for alert in active_alerts:
            stats.alerts_evaluated += 1
            trigger = evaluate_alert(alert, observation, min_drop_pct=settings.alert_min_drop_pct)
            if trigger is None:
                continue
            stats.alerts_fired += 1
            message = _build_alert_email(tracked, alert, trigger, settings=settings)
            try:
                email_sender.send(message)
                stats.emails_sent += 1
            except Exception:  # noqa: BLE001
                stats.errors += 1
                logger.exception("alert email failed", extra={"alert_id": alert.id})
                continue
            alert.status = AlertStatus.fired.value
            alert.last_notified_at = now
            alert.notify_count += 1

    db.flush()
    return stats


def _build_alert_email(
    tracked: TrackedProduct,
    alert: PriceAlert,
    trigger: AlertTrigger,
    *,
    settings: Settings,
) -> EmailMessage:
    name = tracked.title or f"ASIN {tracked.provider_product_id}"
    buy_url = amazon_affiliate_url(
        tracked.provider_product_id,
        market=tracked.market,
        tag=settings.amazon_associate_tag,
    )
    base = settings.public_site_url.rstrip("/")
    unsub_url = f"{base}/alerts/unsubscribe?token={alert.unsubscribe_token}"
    brand = settings.public_brand_name
    body = (
        f"{name}\n"
        f"{trigger.reason}.\n\n"
        f"See it at Amazon: {buy_url}\n\n"
        f"This is a one-time alert — set a new one at {brand} if you want to keep watching.\n"
        f"Price is a snapshot from {trigger.currency}; confirm at the retailer before buying.\n\n"
        f"Stop these emails: {unsub_url}\n"
        f"— {brand} ({settings.public_site_url})"
    )
    return EmailMessage(
        to=alert.email,
        subject=f"Price drop: {name[:80]}",
        text_body=body,
        from_email=settings.alert_from_email,
    )


def _money(cents: int, currency: str) -> str:
    return f"{cents / 100:.2f} {currency}"
