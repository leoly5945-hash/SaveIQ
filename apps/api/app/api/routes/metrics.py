"""Prometheus metrics scrape endpoint (Gate 10B)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.core.settings import Settings, get_settings
from app.observability.metrics import render_metrics

AppSettings = Annotated[Settings, Depends(get_settings)]

router = APIRouter(tags=["metrics"])


def _authorize_metrics(
    settings: Settings,
    x_metrics_token: str | None,
    x_admin_token: str | None,
) -> None:
    expected = settings.metrics_token
    if not expected:
        return
    if x_metrics_token == expected or x_admin_token == settings.admin_api_token:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Metrics token is required.",
    )


@router.get("/metrics")
def metrics(
    settings: AppSettings,
    x_metrics_token: Annotated[str | None, Header()] = None,
    x_admin_token: Annotated[str | None, Header()] = None,
) -> Response:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metrics disabled.")
    _authorize_metrics(settings, x_metrics_token, x_admin_token)
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
