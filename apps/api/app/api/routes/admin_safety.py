"""Admin safety controls — kill switch + auto-tune (Gate 10E / 10I)."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.services.safety.service import TunableHParams, build_safety_service

logger = logging.getLogger(__name__)

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(
    prefix="/admin",
    tags=["admin-safety"],
    dependencies=[Depends(require_admin)],
)


class SafetyConfigRequest(BaseModel):
    kill_switch_enabled: bool | None = None
    auto_tune_enabled: bool | None = None
    manual_override: bool | None = None
    dry_run: bool | None = None
    auto_tune_canary_enabled: bool | None = None
    actions_on_trip: list[str] | None = None


class SafetyEvaluateRequest(BaseModel):
    force_tune: bool = False


class SafetyTripRequest(BaseModel):
    reason: str = Field(default="manual_admin_trip", min_length=1, max_length=500)
    force: bool = True


class SafetyDisarmRequest(BaseModel):
    clear_window: bool = False


class KillSwitchEnableRequest(BaseModel):
    """Arm runtime kill switch. Default trip=true for emergency router fallback.

    FEATURE_KILL_SWITCH env is Render/Blueprint — this endpoint cannot mutate
    process env. It sets the runtime overlay (same as POST /admin/safety/config).
    """

    reason: str = Field(default="admin_kill_switch_enable", min_length=1, max_length=500)
    trip: bool = True
    force: bool = True


class KillSwitchDisableRequest(BaseModel):
    clear_window: bool = False
    unarm: bool = False


class SafetyHParamsRequest(BaseModel):
    epsilon: float | None = Field(default=None, ge=0.0, le=1.0)
    alpha: float | None = Field(default=None, ge=0.0, le=1.0)
    beta: float | None = Field(default=None, ge=0.0, le=1.0)
    gamma: float | None = Field(default=None, ge=0.0, le=1.0)
    cache_ttl_seconds: int | None = Field(default=None, ge=1, le=3600)
    reason: str = Field(default="admin_override", min_length=1, max_length=200)


@router.get("/safety/status")
def get_safety_status(settings: AppSettings) -> dict[str, Any]:
    return build_safety_service(settings).status()


@router.post("/safety/config")
def update_safety_config(body: SafetyConfigRequest, settings: AppSettings) -> dict[str, Any]:
    service = build_safety_service(settings)
    # Env flags remain the source of truth for "allowed"; runtime can only narrow/widen
    # within operator intent. Still allow runtime enable for staging drills when env is on
    # OR when explicitly toggling runtime overlay (documented).
    updated = service.set_config(**body.model_dump(exclude_none=True))
    payload = service.status()
    payload["updated"] = updated
    return payload


@router.post("/safety/evaluate")
def evaluate_safety(
    settings: AppSettings,
    body: SafetyEvaluateRequest | None = None,
) -> dict[str, Any]:
    service = build_safety_service(settings)
    force = bool(body.force_tune) if body is not None else False
    return service.evaluate(force_tune=force)


@router.post("/safety/kill/trip")
def trip_kill_switch(body: SafetyTripRequest, settings: AppSettings) -> dict[str, Any]:
    service = build_safety_service(settings)
    return service.trip(body.reason, force=body.force)


@router.post("/safety/kill/disarm")
def disarm_kill_switch(
    settings: AppSettings,
    body: SafetyDisarmRequest | None = None,
) -> dict[str, Any]:
    service = build_safety_service(settings)
    clear = bool(body.clear_window) if body is not None else False
    return service.disarm(clear_window=clear)


@router.post("/safety/autotune/apply")
def apply_autotune_hparams(body: SafetyHParamsRequest, settings: AppSettings) -> dict[str, Any]:
    service = build_safety_service(settings)
    current = service.get_hparams()
    next_hp = TunableHParams(
        epsilon=current.epsilon if body.epsilon is None else body.epsilon,
        alpha=current.alpha if body.alpha is None else body.alpha,
        beta=current.beta if body.beta is None else body.beta,
        gamma=current.gamma if body.gamma is None else body.gamma,
        cache_ttl_seconds=(
            current.cache_ttl_seconds if body.cache_ttl_seconds is None else body.cache_ttl_seconds
        ),
    )
    try:
        applied = service.set_hparams(next_hp, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"hparams": applied.__dict__, "status": service.status()}


@router.post("/safety/autotune/reset")
def reset_autotune_hparams(settings: AppSettings) -> dict[str, Any]:
    service = build_safety_service(settings)
    hparams = service.reset_hparams(reason="admin_reset")
    return {"hparams": hparams.__dict__, "status": service.status()}


@router.get("/safety/audit")
def get_safety_audit(settings: AppSettings, limit: int = 50) -> dict[str, Any]:
    service = build_safety_service(settings)
    return {"events": service.audit_log(limit=limit)}


def _kill_switch_payload(settings: Settings) -> dict[str, Any]:
    service = build_safety_service(settings)
    status_body = service.status()
    runtime = status_body.get("runtime") or {}
    env = status_body.get("env") or {}
    tripped = bool(runtime.get("tripped"))
    from app.services.router.ai_router import build_ai_router

    router_status = build_ai_router(settings).status()
    return {
        "env_flag": bool(env.get("feature_kill_switch")),
        "armed": bool(runtime.get("kill_switch_enabled")),
        "tripped": tripped,
        "trip_reason": runtime.get("trip_reason"),
        "trip_at": runtime.get("trip_at"),
        "manual_override": bool(runtime.get("manual_override")),
        "auto_tune_enabled": bool(runtime.get("auto_tune_enabled")),
        "router_fallback": tripped,
        "request_router_active": bool(router_status.get("request_router_active")),
        "env_note": (
            "FEATURE_KILL_SWITCH is a Render Blueprint env flag. "
            "This API arms the runtime overlay; durable enablement requires Sync."
        ),
        "safety": status_body,
    }


@router.get("/kill-switch/status")
def get_kill_switch_status(settings: AppSettings) -> dict[str, Any]:
    return _kill_switch_payload(settings)


@router.post("/kill-switch/enable")
def enable_kill_switch(body: KillSwitchEnableRequest, settings: AppSettings) -> dict[str, Any]:
    service = build_safety_service(settings)
    service.set_config(kill_switch_enabled=True, manual_override=False)
    logger.warning(
        "Kill switch ENABLE requested reason=%s trip=%s force=%s env_flag=%s",
        body.reason,
        body.trip,
        body.force,
        settings.feature_kill_switch,
    )
    trip_result: dict[str, Any] | None = None
    if body.trip:
        trip_result = service.trip(body.reason, force=body.force)
        if not trip_result.get("tripped"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=trip_result,
            )
    payload = _kill_switch_payload(settings)
    payload["updated"] = {"kill_switch_enabled": True, "tripped": body.trip}
    payload["trip"] = trip_result
    return payload


@router.post("/kill-switch/disable")
def disable_kill_switch(
    settings: AppSettings,
    body: KillSwitchDisableRequest | None = None,
) -> dict[str, Any]:
    service = build_safety_service(settings)
    clear = bool(body.clear_window) if body is not None else False
    unarm = bool(body.unarm) if body is not None else False
    disarm_result = service.disarm(clear_window=clear)
    if unarm:
        service.set_config(kill_switch_enabled=False)
    logger.warning("Kill switch DISABLE unarm=%s clear_window=%s", unarm, clear)
    payload = _kill_switch_payload(settings)
    payload["updated"] = {
        "tripped": False,
        "kill_switch_enabled": False if unarm else payload["armed"],
    }
    payload["disarm"] = disarm_result
    return payload
