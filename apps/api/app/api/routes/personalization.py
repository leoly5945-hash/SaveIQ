"""Public personalization status (Gate 8)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.settings import Settings, get_settings
from app.services.user.profile import build_user_profile_service

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/personalization", tags=["personalization"])


class PersonalizationStatusResponse(BaseModel):
    feature_enabled: bool
    cache_enabled: bool
    cache_ttl_seconds: int
    embedding_dim: int
    pii_policy: str


@router.get("/status", response_model=PersonalizationStatusResponse)
def get_personalization_status(settings: AppSettings) -> PersonalizationStatusResponse:
    return PersonalizationStatusResponse(**build_user_profile_service(settings).status())
