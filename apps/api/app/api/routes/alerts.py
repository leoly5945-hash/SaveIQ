"""Public price-alert endpoints (CP15).

Only the unsubscribe link is public for now — it is emailed to users and must
work without an account. Creating alerts from the public site is CP16.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.tracking.service import unsubscribe

router = APIRouter(prefix="/alerts", tags=["alerts"])


class UnsubscribeResponse(BaseModel):
    ok: bool
    message: str


@router.get("/unsubscribe", response_model=UnsubscribeResponse)
def unsubscribe_alert(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Query(min_length=16, max_length=64)],
) -> UnsubscribeResponse:
    unsubscribe(db, token)
    db.commit()
    # Same response whether or not the token matched — don't confirm token validity.
    return UnsubscribeResponse(
        ok=True,
        message="You're unsubscribed from that price alert.",
    )
