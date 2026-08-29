from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.services.affiliate.attribution import record_conversion

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/affiliate", tags=["affiliate"])


class PostbackResult(BaseModel):
    stored: bool
    conversion_id: int
    network: str
    status: str
    matched_click_event_id: int | None
    subid: str | None


@router.post("/postback/{network}", response_model=PostbackResult)
async def receive_conversion_postback(
    network: str,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    secret: str = Query(default=""),
) -> PostbackResult:
    """Ingest an affiliate network's server-to-server conversion postback.

    Auth is a shared ``?secret=`` matching ``AFFILIATE_POSTBACK_SECRET``. The
    raw payload (JSON body or form-encoded) is stored verbatim as evidence.
    """
    expected = settings.affiliate_postback_secret
    if not expected:
        raise HTTPException(status_code=503, detail="Postback ingestion is not configured")
    if not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=401, detail="Invalid postback secret")

    payload: dict[str, Any]
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Body is not valid JSON") from exc
        payload = body if isinstance(body, dict) else {"_raw": body}
    else:
        form = await request.form()
        payload = {key: str(value) for key, value in form.multi_items()}
        if not payload:
            payload = dict(request.query_params)
            payload.pop("secret", None)

    conversion = record_conversion(db, network=network, payload=payload)
    return PostbackResult(
        stored=True,
        conversion_id=conversion.id,
        network=conversion.network,
        status=conversion.status,
        matched_click_event_id=conversion.click_event_id,
        subid=conversion.subid,
    )
