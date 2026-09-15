"""Public price-alert endpoints (CP15 + CP16 + CP-watchlist).

``POST /alerts`` creates a one-shot alert from a URL / ASIN + email.
``GET /alerts`` lists everything an email has ever tracked — the "watchlist" —
with each item's live price/verdict, not just whether its one-shot alert has
fired. ``GET /alerts/unsubscribe`` deactivates one alert from the emailed link.
All three are unauthenticated (email is the only identifier, matching the
rest of the site's no-account design); ``POST`` and ``GET`` (list) are per-IP
rate limited (only when RATE_LIMIT_ENABLED) — ``POST`` because it spends a
provider token, ``GET`` to keep the email param from being brute-forced into a
directory of who's watching what.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.models.tracking import AlertKind, AlertStatus, PriceAlert
from app.providers import get_provider_registry
from app.services.decision.price_check import PriceCheckError
from app.services.endpoint_limit import allow
from app.services.tracking.service import (
    TrackingError,
    amazon_affiliate_url,
    latest_observation,
    normalize_email,
    track_and_alert,
    unsubscribe,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])

DbSession = Annotated[Session, Depends(get_db)]


class CreateAlertRequest(BaseModel):
    email: str
    url: str | None = None
    product_id: str | None = None
    kind: AlertKind = AlertKind.any_drop
    threshold_cents: int | None = Field(default=None, ge=1)


class CreateAlertResponse(BaseModel):
    id: int
    kind: str
    status: str
    baseline_cents: int | None
    product_title: str | None
    provider_product_id: str
    unsubscribe_url: str


class UnsubscribeResponse(BaseModel):
    ok: bool
    message: str


class WatchlistItemOut(BaseModel):
    alert_id: int
    provider_product_id: str
    title: str | None
    product_url: str | None
    buy_url: str | None
    currency: str
    price_cents: int | None
    verdict: str | None
    kind: str
    status: str
    unsubscribe_url: str


class WatchlistResponse(BaseModel):
    items: list[WatchlistItemOut]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("", response_model=CreateAlertResponse, status_code=201)
async def create_alert_public(
    body: CreateAlertRequest,
    request: Request,
    db: DbSession,
) -> CreateAlertResponse:
    settings: Settings = get_settings()
    if not allow("alert", _client_ip(request), per_minute=settings.alert_create_rate_per_minute):
        raise HTTPException(status_code=429, detail="too many alerts — try again in a minute")

    try:
        alert, tracked = await track_and_alert(
            db,
            get_provider_registry(),
            email=body.email,
            kind=body.kind,
            threshold_cents=body.threshold_cents,
            product_id=body.product_id,
            url=body.url,
        )
    except PriceCheckError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    db.commit()
    base = settings.public_site_url.rstrip("/")
    return CreateAlertResponse(
        id=alert.id,
        kind=alert.kind,
        status=alert.status,
        baseline_cents=alert.baseline_cents,
        product_title=tracked.title,
        provider_product_id=tracked.provider_product_id,
        unsubscribe_url=f"{base}/alerts/unsubscribe?token={alert.unsubscribe_token}",
    )


@router.get("", response_model=WatchlistResponse)
def list_watchlist(
    db: DbSession,
    request: Request,
    email: Annotated[str, Query(min_length=3, max_length=320)],
) -> WatchlistResponse:
    """Everything ``email`` has ever tracked, each with its live price/verdict.

    Deliberately independent of whether a given alert has already fired —
    alerts are one-shot (CP15), but the watchlist is meant to be revisited,
    so it shows the tracked product's *current* state every time, not "did
    your one email already go out".
    """

    settings: Settings = get_settings()
    if not allow("watchlist", _client_ip(request), per_minute=settings.watchlist_rate_per_minute):
        raise HTTPException(status_code=429, detail="too many requests — try again in a minute")

    try:
        normalized = normalize_email(email)
    except TrackingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    alerts = list(
        db.execute(
            select(PriceAlert)
            .where(
                PriceAlert.email == normalized,
                PriceAlert.status != AlertStatus.unsubscribed.value,
            )
            .order_by(PriceAlert.created_at.desc())
        ).scalars()
    )

    base = settings.public_site_url.rstrip("/")
    items: list[WatchlistItemOut] = []
    for alert in alerts:
        tracked = alert.tracked_product
        observation = latest_observation(db, tracked)
        buy_url = tracked.product_url
        if tracked.provider == "keepa":
            buy_url = amazon_affiliate_url(
                tracked.provider_product_id,
                market=tracked.market,
                tag=settings.amazon_associate_tag,
            )
        items.append(
            WatchlistItemOut(
                alert_id=alert.id,
                provider_product_id=tracked.provider_product_id,
                title=tracked.title,
                product_url=tracked.product_url,
                buy_url=buy_url,
                currency=observation.currency if observation else "CAD",
                price_cents=observation.effective_price_cents if observation else None,
                verdict=observation.verdict if observation else None,
                kind=alert.kind,
                status=alert.status,
                unsubscribe_url=f"{base}/alerts/unsubscribe?token={alert.unsubscribe_token}",
            )
        )
    return WatchlistResponse(items=items)


@router.get("/unsubscribe", response_model=UnsubscribeResponse)
def unsubscribe_alert(
    db: DbSession,
    token: Annotated[str, Query(min_length=16, max_length=64)],
) -> UnsubscribeResponse:
    unsubscribe(db, token)
    db.commit()
    # Same response whether or not the token matched — don't confirm token validity.
    return UnsubscribeResponse(ok=True, message="You're unsubscribed from that price alert.")
