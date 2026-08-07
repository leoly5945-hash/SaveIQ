"""Request logging + HTTP Prometheus metrics (Gate 10B)."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.settings import get_settings
from app.observability.metrics import observe_http_request

SKIP_DETAILED_PATHS = frozenset({"/health", "/metrics"})


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        settings = get_settings()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            service=settings.app_name,
            path=request.url.path,
            method=request.method,
        )

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-Id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_s = time.perf_counter() - started
            if settings.metrics_enabled:
                observe_http_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_seconds=duration_s,
                )
            if request.url.path not in SKIP_DETAILED_PATHS:
                log = structlog.get_logger("http")
                anonymous = request.headers.get("x-anonymous-user-id")
                log.info(
                    "request_completed",
                    status_code=status_code,
                    duration_ms=round(duration_s * 1000, 3),
                    anonymous_user_id=anonymous,
                )
