"""Public sanitized bandit status (Gate 7)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.settings import Settings, get_settings
from app.services.bandit.service import build_bandit_router_service

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/bandit", tags=["bandit"])


class PublicBanditStatusResponse(BaseModel):
    active: bool
    mode: str
    logging_only: bool
    controls_routing: bool
    algorithm: str | None
    ready: bool
    sample_count: int


@router.get("/status", response_model=PublicBanditStatusResponse)
def get_public_bandit_status(settings: AppSettings) -> PublicBanditStatusResponse:
    status = build_bandit_router_service(settings).public_status()
    return PublicBanditStatusResponse(**status)
