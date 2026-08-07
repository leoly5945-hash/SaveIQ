"""Admin rate-limit status endpoint (Gate 10A)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.services.rate_limit import get_rate_limiter

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(
    prefix="/admin",
    tags=["admin-rate-limit"],
    dependencies=[Depends(require_admin)],
)


class RateLimitStatusResponse(BaseModel):
    enabled: bool
    store: str
    public_per_minute: int
    auth_per_minute: int
    admin_per_minute: int
    window_seconds: int


@router.get("/rate-limit/status", response_model=RateLimitStatusResponse)
def get_rate_limit_status(settings: AppSettings) -> RateLimitStatusResponse:
    limiter = get_rate_limiter(
        enabled=settings.rate_limit_enabled,
        public_per_minute=settings.rate_limit_public_per_minute,
        auth_per_minute=settings.rate_limit_auth_per_minute,
        admin_per_minute=settings.rate_limit_admin_per_minute,
        redis_url=settings.redis_url,
    )
    return RateLimitStatusResponse(
        enabled=limiter.config.enabled,
        store=limiter.store_name,
        public_per_minute=limiter.config.public_per_minute,
        auth_per_minute=limiter.config.auth_per_minute,
        admin_per_minute=limiter.config.admin_per_minute,
        window_seconds=60,
    )
