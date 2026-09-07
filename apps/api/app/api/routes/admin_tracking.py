"""Admin: create + drive price alerts (CP15).

The public ``POST /alerts`` + rate limiting + UI is CP16; this admin surface is
enough to exercise the whole track -> observe -> alert -> email flow on staging.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.models.tracking import AlertKind, PriceAlert, TrackedProduct
from app.providers import ProviderError, get_provider_registry
from app.services.decision.assess import assess_from_provider
from app.services.product_url import extract_product_ref
from app.services.tracking.email import get_email_sender
from app.services.tracking.service import (
    CycleStats,
    TrackingError,
    create_alert,
    get_or_create_tracked_product,
    record_observation,
    run_alert_cycle,
)

logger = logging.getLogger(__name__)

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(
    prefix="/admin/alerts",
    tags=["admin-alerts"],
    dependencies=[Depends(require_admin)],
)


class CreateAlertRequest(BaseModel):
    email: str
    url: str | None = None
    product_id: str | None = None
    kind: AlertKind = AlertKind.any_drop
    threshold_cents: int | None = Field(default=None, ge=1)


class AlertResponse(BaseModel):
    id: int
    email: str
    kind: str
    status: str
    threshold_cents: int | None
    baseline_cents: int | None
    last_notified_at: str | None
    notify_count: int
    product_title: str | None
    provider_product_id: str
    unsubscribe_url: str


class AlertListResponse(BaseModel):
    count: int
    alerts: list[AlertResponse]


def _unsub_url(settings: Settings, token: str) -> str:
    return f"{settings.public_site_url.rstrip('/')}/alerts/unsubscribe?token={token}"


def _to_response(alert: PriceAlert, tracked: TrackedProduct, settings: Settings) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        email=alert.email,
        kind=alert.kind,
        status=alert.status,
        threshold_cents=alert.threshold_cents,
        baseline_cents=alert.baseline_cents,
        last_notified_at=alert.last_notified_at.isoformat() if alert.last_notified_at else None,
        notify_count=alert.notify_count,
        product_title=tracked.title,
        provider_product_id=tracked.provider_product_id,
        unsubscribe_url=_unsub_url(settings, alert.unsubscribe_token),
    )


@router.post("", response_model=AlertResponse, status_code=201)
async def create_price_alert(
    body: CreateAlertRequest,
    db: DbSession,
    settings: AppSettings,
) -> AlertResponse:
    if not body.url and not body.product_id:
        raise HTTPException(status_code=422, detail="pass url or product_id")

    asin = (body.product_id or "").strip().upper()
    market = "CA"
    if body.url:
        ref = extract_product_ref(body.url, follow_redirects=True)
        if ref is None:
            raise HTTPException(status_code=422, detail="could not find a product id in that URL")
        if ref.market not in ("", "CA"):
            raise HTTPException(status_code=422, detail="only Amazon.ca is covered right now")
        asin = ref.product_id
        market = ref.market or "CA"
    if not asin:
        raise HTTPException(status_code=422, detail="no product id")

    registry = get_provider_registry()
    adapter = registry.try_get("keepa")
    if adapter is None:
        raise HTTPException(status_code=503, detail="no keepa provider configured")

    try:
        product = await adapter.get_product(asin)
        price = await adapter.get_price(asin)
        history = await adapter.get_price_history(asin, days=90)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"provider error: {exc}") from exc

    tracked = get_or_create_tracked_product(
        db,
        provider="keepa",
        provider_product_id=asin,
        market=market,
        title=product.title if product else None,
        product_url=product.product_url if product else None,
    )

    if price is not None and price.price_cents is not None and history is not None:
        assessment = assess_from_provider(price, history)
        avg90 = None
        verdict = None
        score = None
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
        alert = create_alert(
            db,
            tracked,
            email=body.email,
            kind=body.kind,
            threshold_cents=body.threshold_cents,
        )
    except TrackingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    return _to_response(alert, tracked, settings)


@router.get("", response_model=AlertListResponse)
def list_price_alerts(db: DbSession, settings: AppSettings) -> AlertListResponse:
    rows = db.execute(
        select(PriceAlert, TrackedProduct)
        .join(TrackedProduct, PriceAlert.tracked_product_id == TrackedProduct.id)
        .order_by(PriceAlert.created_at.desc())
        .limit(200)
    ).all()
    return AlertListResponse(
        count=len(rows),
        alerts=[_to_response(alert, tracked, settings) for alert, tracked in rows],
    )


@router.post("/run")
async def run_price_alert_cycle(db: DbSession, settings: AppSettings) -> CycleStats:
    registry = get_provider_registry()
    stats = await run_alert_cycle(
        db,
        registry,
        email_sender=get_email_sender(settings),
        settings=settings,
    )
    db.commit()
    return stats
