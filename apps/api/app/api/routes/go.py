from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.services.affiliate.attribution import looks_like_bot, resolve_redirect

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/go", tags=["go"])


@router.get("/{offer_id}")
def redirect_to_offer(
    offer_id: int,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    t: str = Query(default="affiliate"),
    aid: str | None = Query(default=None),
    user_agent: Annotated[str | None, Header(alias="user-agent")] = None,
    referer: Annotated[str | None, Header(alias="referer")] = None,
    x_forwarded_for: Annotated[str | None, Header(alias="x-forwarded-for")] = None,
    sec_purpose: Annotated[str | None, Header(alias="sec-purpose")] = None,
    x_purpose: Annotated[str | None, Header(alias="x-purpose")] = None,
    purpose: Annotated[str | None, Header(alias="purpose")] = None,
) -> RedirectResponse:
    """Log the click server-side, then 302 to the affiliate URL with our SubID."""
    client_ip = x_forwarded_for or (request.client.host if request.client else None)
    is_bot = looks_like_bot(user_agent, sec_purpose=sec_purpose, purpose=x_purpose or purpose)
    salt = settings.affiliate_postback_secret or settings.admin_api_token

    resolution = resolve_redirect(
        db,
        offer_id=offer_id,
        target_type=t,
        user_agent=user_agent,
        referrer=referer,
        client_ip=client_ip,
        anonymous_user_id=aid,
        salt=salt,
        dedup_seconds=settings.affiliate_redirect_dedup_seconds,
        is_bot=is_bot,
    )
    if resolution is None:
        raise HTTPException(status_code=404, detail="No trackable destination for this offer")

    response = RedirectResponse(url=resolution.target_url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
