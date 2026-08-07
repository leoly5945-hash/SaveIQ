"""Admin canary control endpoints (Gate 10C)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.services.canary.service import CANARY_FEATURES, build_canary_service

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(
    prefix="/admin",
    tags=["admin-canary"],
    dependencies=[Depends(require_admin)],
)


class CanaryStatusResponse(BaseModel):
    enabled: bool
    percentage: int
    features: list[str]
    sticky_session: bool
    phases: dict[str, int]
    env_defaults: dict[str, Any]


class CanaryConfigRequest(BaseModel):
    enabled: bool | None = None
    percentage: int | None = Field(default=None, ge=0, le=100)
    features: list[str] | None = None
    sticky_session: bool | None = None


class CanaryStatsResponse(BaseModel):
    config: dict[str, Any]
    assignments: dict[str, int]
    notes: list[str]


@router.get("/canary/status", response_model=CanaryStatusResponse)
def get_canary_status(settings: AppSettings) -> CanaryStatusResponse:
    service = build_canary_service(settings)
    config = service.get_config()
    return CanaryStatusResponse(
        enabled=config.enabled,
        percentage=config.percentage,
        features=config.normalized_features(),
        sticky_session=config.sticky_session,
        phases={"C0": 0, "C1": 1, "C2": 5, "C3": 25, "C4": 100},
        env_defaults={
            "CANARY_ENABLED": settings.canary_enabled,
            "CANARY_PERCENTAGE": settings.canary_percentage,
            "CANARY_FEATURES": settings.canary_features,
            "CANARY_STICKY_SESSION": settings.canary_sticky_session,
        },
    )


@router.post("/canary/config", response_model=CanaryStatusResponse)
def update_canary_config(
    body: CanaryConfigRequest,
    settings: AppSettings,
) -> CanaryStatusResponse:
    if body.features is not None:
        unknown = [f for f in body.features if f not in CANARY_FEATURES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown canary features: {unknown}. Allowed: {list(CANARY_FEATURES)}",
            )
    service = build_canary_service(settings)
    config = service.set_config(
        enabled=body.enabled,
        percentage=body.percentage,
        features=body.features,
        sticky_session=body.sticky_session,
    )
    return CanaryStatusResponse(
        enabled=config.enabled,
        percentage=config.percentage,
        features=config.normalized_features(),
        sticky_session=config.sticky_session,
        phases={"C0": 0, "C1": 1, "C2": 5, "C3": 25, "C4": 100},
        env_defaults={
            "CANARY_ENABLED": settings.canary_enabled,
            "CANARY_PERCENTAGE": settings.canary_percentage,
            "CANARY_FEATURES": settings.canary_features,
            "CANARY_STICKY_SESSION": settings.canary_sticky_session,
        },
    )


@router.get("/canary/stats", response_model=CanaryStatsResponse)
def get_canary_stats(settings: AppSettings) -> CanaryStatsResponse:
    service = build_canary_service(settings)
    payload = service.stats()
    return CanaryStatsResponse(
        config=payload["config"],
        assignments=payload["assignments"],
        notes=[
            "Compare Prometheus series with label canary=true|false|off "
            "(http_requests_total, llm_request_duration_seconds, llm_cost_usd_total).",
            "Rollback: POST /admin/canary/config with enabled=false and percentage=0.",
        ],
    )
