from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.click_tracking import ClickTrackingInput, record_click

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/clicks", tags=["clicks"])


class ClickRequest(BaseModel):
    offer_id: int = Field(ge=1)
    target_type: str = Field(max_length=40)
    referrer: str | None = Field(default=None, max_length=2048)


class ClickResponse(BaseModel):
    id: int
    offer_id: int | None
    target_type: str
    target_url: str
    provider_source: str
    source_record_id: str
    market: str


@router.post("", response_model=ClickResponse, status_code=201)
def create_click(
    db: DbSession,
    payload: ClickRequest,
    user_agent: Annotated[str | None, Header(alias="user-agent")] = None,
) -> ClickResponse:
    try:
        result = record_click(
            db,
            ClickTrackingInput(
                offer_id=payload.offer_id,
                target_type=payload.target_type,
                referrer=payload.referrer,
                user_agent=user_agent,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Trackable offer target not found")
    return ClickResponse(**result)
