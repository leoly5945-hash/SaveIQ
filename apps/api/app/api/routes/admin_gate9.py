"""Admin Gate 9 endpoints: models status, benchmark, policy switch."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.services.bandit.service import build_bandit_router_service
from app.services.router.ai_router import build_ai_router

AppSettings = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(
    prefix="/admin",
    tags=["admin-gate9"],
    dependencies=[Depends(require_admin)],
)


class SwitchPolicyRequest(BaseModel):
    policy: Literal["rule", "linucb", "neural", "rlhf"] = Field(
        description="Runtime router policy override (feature-gated for neural/rlhf)."
    )


class BenchmarkRunRequest(BaseModel):
    limit: int = Field(default=2000, ge=1, le=50000)


@router.get("/models/status")
def get_models_status(settings: AppSettings) -> dict[str, Any]:
    router_status = build_ai_router(settings).status()
    configured = router_status.get("providers_configured") or {}
    metrics = build_ai_router(settings).metrics_snapshot()
    providers_metrics = metrics.get("providers") or {}
    models = []
    for name, is_configured in dict(configured).items():
        provider_metrics = providers_metrics.get(name) or {}
        models.append(
            {
                "provider": name,
                "configured": bool(is_configured),
                "average_latency_ms": provider_metrics.get("avg_latency_ms", 0),
                "requests": provider_metrics.get("requests", 0),
                "errors": provider_metrics.get("errors", 0),
                "estimated_cost_usd": provider_metrics.get("estimated_cost_usd", 0),
            }
        )
    return {
        "chinese_providers_enabled": settings.feature_chinese_llm_providers,
        "router_mode": settings.ai_router_mode,
        "models": models,
        # Never expose raw keys — booleans only.
        "keys_present": {
            "openai": bool(settings.openai_api_key),
            "anthropic": bool(settings.anthropic_api_key),
            "deepseek": bool(settings.deepseek_api_key),
            "dashscope": bool(settings.dashscope_api_key),
            "baidu": bool(settings.baidu_api_key and settings.baidu_secret_key),
        },
    }


@router.get("/benchmark/results")
def get_benchmark_results(settings: AppSettings) -> dict[str, Any]:
    return build_bandit_router_service(settings).benchmark_results()


@router.post("/benchmark/run")
def run_benchmark(
    settings: AppSettings,
    db: DbSession,
    payload: BenchmarkRunRequest | None = None,
) -> dict[str, Any]:
    limit = payload.limit if payload is not None else 2000
    return build_bandit_router_service(settings).run_benchmark(limit=limit, db=db)


@router.post("/bandit/switch_policy")
def switch_bandit_policy(
    payload: SwitchPolicyRequest,
    settings: AppSettings,
) -> dict[str, Any]:
    try:
        return build_bandit_router_service(settings).switch_policy(payload.policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
