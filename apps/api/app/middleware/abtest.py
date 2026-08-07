"""Bind sticky A/B group onto the request (Gate 10D)."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.settings import get_settings
from app.services.abtest.context import bind_abtest_request, clear_abtest_request
from app.services.abtest.service import build_abtest_service
from app.services.user.identity import normalize_anonymous_user_id


class ABTestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        settings = get_settings()
        service = build_abtest_service(settings)

        user_id = self._extract_user_id(request)
        group = "none"
        experiment = service.active_experiment_name()
        overrides = None
        if user_id and service.feature_enabled and service.status().get("running"):
            assignment = service.get_config(user_id)
            group = str(assignment.get("group") or "none")
            experiment = str(assignment.get("experiment") or experiment)
            overrides = assignment.get("config") or {}
            if group != "none":
                service.log_exposure(user_id, group, experiment)

        bind_abtest_request(
            user_id=user_id,
            group=group,
            experiment=experiment,
            overrides=overrides if isinstance(overrides, dict) else None,
        )
        request.state.ab_group = group
        request.state.ab_experiment = experiment
        request.state.ab_user_id = user_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-AB-Group"] = group
                if experiment:
                    headers["X-AB-Experiment"] = str(experiment)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_abtest_request()

    def _extract_user_id(self, request: Request) -> str | None:
        raw = request.headers.get("x-user-id") or request.headers.get("x-anonymous-user-id")
        if not raw:
            return None
        try:
            return normalize_anonymous_user_id(raw)
        except ValueError:
            # Accept opaque X-User-ID that may not match anon rules (still sticky).
            cleaned = raw.strip()
            return cleaned[:64] if cleaned else None
