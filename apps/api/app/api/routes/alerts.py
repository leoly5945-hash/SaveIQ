"""Public price-alert endpoints (CP15 + CP16).

``POST /alerts`` creates a one-shot alert from a URL / ASIN + email.
``GET /alerts/unsubscribe`` deactivates one from the emailed link. Both are
unauthenticated; ``POST`` is per-IP rate limited (only when RATE_LIMIT_ENABLED)
because it spends a provider token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.models.tracking import AlertKind
from app.providers import get_provider_registry
from app.services.decision.price_check import PriceCheckError
from app.services.endpoint_limit import allow
from app.services.tracking.service import track_and_alert, unsubscribe

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


@router.get("/unsubscribe", response_model=UnsubscribeResponse)
def unsubscribe_alert(
    db: DbSession,
    token: Annotated[str, Query(min_length=16, max_length=64)],
) -> UnsubscribeResponse:
    unsubscribe(db, token)
    db.commit()
    # Same response whether or not the token matched — don't confirm token validity.
    return UnsubscribeResponse(ok=True, message="You're unsubscribed from that price alert.")
