"""ASGI middleware applying Gate 10A rate limits."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.settings import get_settings
from app.services.rate_limit import Bucket, get_rate_limiter
from app.services.user.identity import normalize_anonymous_user_id

EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


def classify_bucket(path: str, anonymous_user_id: str | None) -> tuple[Bucket, str]:
    if path.startswith("/admin"):
        return "admin", "admin"
    if anonymous_user_id:
        return "auth", f"user:{anonymous_user_id}"
    return "public", "ip"


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        path = request.url.path
        if path in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        limiter = get_rate_limiter(
            enabled=settings.rate_limit_enabled,
            public_per_minute=settings.rate_limit_public_per_minute,
            auth_per_minute=settings.rate_limit_auth_per_minute,
            admin_per_minute=settings.rate_limit_admin_per_minute,
            redis_url=settings.redis_url,
        )
        if not limiter.config.enabled:
            await self.app(scope, receive, send)
            return

        anonymous_raw = request.headers.get("x-anonymous-user-id")
        anonymous_id: str | None = None
        if anonymous_raw:
            try:
                anonymous_id = normalize_anonymous_user_id(anonymous_raw)
            except ValueError:
                anonymous_id = None

        bucket, identity_prefix = classify_bucket(path, anonymous_id)
        client_host = request.client.host if request.client else "unknown"
        if bucket in {"public", "admin"}:
            identity = f"{identity_prefix}:{client_host}"
        else:
            identity = identity_prefix

        decision = limiter.check(bucket, identity)
        if not decision.allowed:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded.",
                    "bucket": decision.bucket,
                    "limit": decision.limit,
                    "reset_seconds": decision.reset_seconds,
                },
                headers={
                    "Retry-After": str(decision.reset_seconds),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(decision.reset_seconds),
                },
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(decision.limit)
                headers["X-RateLimit-Remaining"] = str(decision.remaining)
                headers["X-RateLimit-Reset"] = str(decision.reset_seconds)
            await send(message)

        await self.app(scope, receive, send_with_headers)
