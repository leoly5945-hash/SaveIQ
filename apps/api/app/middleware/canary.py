"""Bind request identity into canary context (Gate 10C)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.settings import get_settings
from app.services.canary.context import bind_canary_request, clear_canary_request
from app.services.canary.service import build_canary_service
from app.services.user.identity import normalize_anonymous_user_id


class CanaryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        settings = get_settings()
        service = build_canary_service(settings)

        anonymous_id: str | None = None
        raw = request.headers.get("x-anonymous-user-id")
        if raw:
            try:
                anonymous_id = normalize_anonymous_user_id(raw)
            except ValueError:
                anonymous_id = None
        client_ip = request.client.host if request.client else None
        identity = service.identity_for(anonymous_id, client_ip)
        cohort = service.cohort_for(identity)
        bind_canary_request(identity=identity, cohort=cohort)
        if request.url.path not in {"/health", "/metrics"}:
            service.record_assignment(cohort)

        try:
            await self.app(scope, receive, send)
        finally:
            clear_canary_request()
