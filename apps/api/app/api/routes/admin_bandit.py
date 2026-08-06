"""Admin contextual bandit endpoints (Gate 7)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.services.bandit.service import build_bandit_router_service, reset_bandit_singleton

AppSettings = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(
    prefix="/admin/bandit",
    tags=["admin-bandit"],
    dependencies=[Depends(require_admin)],
)


class BanditTrainRequest(BaseModel):
    limit: int = Field(default=5000, ge=1, le=50000)


class BanditStatusResponse(BaseModel):
    feature_enabled: bool
    mode: str
    active: bool
    logging_only: bool
    controls_routing: bool
    features: list[str]
    agent: dict[str, Any]
    reward_weights: dict[str, float]
    log_count: int
    offline_evaluation: dict[str, Any]
    policy: str | None = None
    neural: dict[str, Any] | None = None
    rlhf: dict[str, Any] | None = None
    flags: dict[str, Any] | None = None
    bayesian_tuning: dict[str, Any] | None = None


@router.get("/status", response_model=BanditStatusResponse)
def get_bandit_status(settings: AppSettings) -> BanditStatusResponse:
    status = build_bandit_router_service(settings).status()
    return BanditStatusResponse(**status)


@router.post("/train")
def train_bandit(
    settings: AppSettings,
    db: DbSession,
    payload: BanditTrainRequest | None = None,
) -> dict[str, Any]:
    limit = payload.limit if payload is not None else 5000
    result = build_bandit_router_service(settings).train_from_logs(limit=limit, db=db)
    return result


@router.post("/reset")
def reset_bandit(settings: AppSettings) -> dict[str, Any]:
    reset_bandit_singleton()
    return build_bandit_router_service(settings).reset()


@router.get("/metrics")
def get_bandit_metrics(settings: AppSettings) -> dict[str, Any]:
    return build_bandit_router_service(settings).metrics()
