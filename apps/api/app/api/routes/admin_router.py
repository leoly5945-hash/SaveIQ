"""Admin AI router status, metrics, and config endpoints (Gate 6A/6B)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.services.router.ai_router import build_ai_router

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(
    prefix="/admin",
    tags=["admin-router"],
    dependencies=[Depends(require_admin)],
)


class AiRouterStatusResponse(BaseModel):
    active: bool
    mode: str
    strategy: str
    default_model: str
    live_ready: bool
    available_models: list[str]
    providers_configured: dict[str, bool]
    cache_enabled: bool
    fallback_provider: str
    bandit: dict[str, object] | None = None
    chinese_providers_enabled: bool = False
    request_router_active: bool | None = None
    kill_switch_tripped: bool = False
    kill_switch_fallback: bool = False


class AiRouterMetricsResponse(BaseModel):
    providers: dict[str, dict[str, float | int]]
    cache_hits: int
    cache_misses: int


class AiRouterConfigResponse(BaseModel):
    strategy: str
    mode: str
    fallback_provider: str
    cache_enabled: bool
    cache_ttl_seconds: int
    feature_enabled: bool


class AiRouterConfigUpdateRequest(BaseModel):
    strategy: Literal["cost_optimized", "quality_optimized"] = Field(
        description="Runtime routing strategy override stored in Redis/memory."
    )


@router.get("/router-status", response_model=AiRouterStatusResponse)
def get_router_status(settings: AppSettings) -> AiRouterStatusResponse:
    """Report AI router enablement without exposing secrets."""
    status = build_ai_router(settings).status()
    return AiRouterStatusResponse(**status)


@router.get("/router/metrics", response_model=AiRouterMetricsResponse)
def get_router_metrics(settings: AppSettings) -> AiRouterMetricsResponse:
    snapshot = build_ai_router(settings).metrics_snapshot()
    return AiRouterMetricsResponse(**snapshot)


@router.get("/router/config", response_model=AiRouterConfigResponse)
def get_router_config(settings: AppSettings) -> AiRouterConfigResponse:
    config = build_ai_router(settings).get_config()
    return AiRouterConfigResponse(**config)


@router.put("/router/config", response_model=AiRouterConfigResponse)
def update_router_config(
    payload: AiRouterConfigUpdateRequest,
    settings: AppSettings,
) -> AiRouterConfigResponse:
    """Update runtime strategy only. Does not enable live mode or accept secrets."""
    try:
        config = build_ai_router(settings).set_strategy(payload.strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AiRouterConfigResponse(**config)
