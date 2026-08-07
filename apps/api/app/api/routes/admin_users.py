"""Admin anonymous-user personalization stats (Gate 8)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.services.user.profile import build_user_profile_service

AppSettings = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


@router.get("/stats")
def get_user_stats(settings: AppSettings, db: DbSession) -> dict[str, Any]:
    return build_user_profile_service(settings).stats(db=db)
