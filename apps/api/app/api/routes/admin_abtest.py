"""Admin A/B testing controls (Gate 10D)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.services.abtest.service import build_abtest_service

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(
    prefix="/admin",
    tags=["admin-abtest"],
    dependencies=[Depends(require_admin)],
)


class ABTestStartRequest(BaseModel):
    experiment: str | None = None


class ABTestConfigRequest(BaseModel):
    feature_enabled: bool | None = None
    running: bool | None = None
    active_experiment: str | None = None
    experiment: dict[str, Any] | None = None
    reload: bool | None = None


class ABTestSignificanceRequest(BaseModel):
    experiment: str | None = None
    metric: str = Field(default="conversions")


@router.get("/abtest/status")
def get_abtest_status(settings: AppSettings) -> dict[str, Any]:
    service = build_abtest_service(settings)
    payload = service.status()
    payload["stats"] = service.get_stats()
    return payload


@router.post("/abtest/start")
def start_abtest(settings: AppSettings, body: ABTestStartRequest | None = None) -> dict[str, Any]:
    service = build_abtest_service(settings)
    try:
        return service.start(None if body is None else body.experiment)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/abtest/stop")
def stop_abtest(settings: AppSettings) -> dict[str, Any]:
    service = build_abtest_service(settings)
    return service.stop()


@router.post("/abtest/config")
def update_abtest_config(body: ABTestConfigRequest, settings: AppSettings) -> dict[str, Any]:
    service = build_abtest_service(settings)
    try:
        return service.update_config(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/abtest/significance")
def get_abtest_significance(
    settings: AppSettings,
    experiment: str | None = None,
    metric: str = "conversions",
) -> dict[str, Any]:
    service = build_abtest_service(settings)
    return service.calculate_significance(experiment, metric)


@router.post("/abtest/significance")
def post_abtest_significance(
    body: ABTestSignificanceRequest,
    settings: AppSettings,
) -> dict[str, Any]:
    service = build_abtest_service(settings)
    return service.calculate_significance(body.experiment, body.metric)
