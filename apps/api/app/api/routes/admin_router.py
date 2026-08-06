"""Admin AI router status endpoint (Gate 6A)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.services.router.contract import AI_ROUTER_AVAILABLE_MODELS

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(
    prefix="/admin",
    tags=["admin-router"],
    dependencies=[Depends(require_admin)],
)


class AiRouterStatusResponse(BaseModel):
    active: bool
    mode: str
    default_model: str
    live_ready: bool
    available_models: list[str]


@router.get("/router-status", response_model=AiRouterStatusResponse)
def get_router_status(settings: AppSettings) -> AiRouterStatusResponse:
    """Report mock AI router enablement without exposing secrets."""
    active = settings.feature_ai_router and settings.ai_router_mode == "mock"
    return AiRouterStatusResponse(
        active=active,
        mode=settings.ai_router_mode,
        default_model=settings.ai_router_default_model,
        live_ready=False,
        available_models=list(AI_ROUTER_AVAILABLE_MODELS),
    )
