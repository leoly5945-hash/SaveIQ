"""IP / anonymous-user rate limiting with Redis + in-memory fallback."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

from app.services.router.redis_client import create_redis_client

logger = logging.getLogger(__name__)

Bucket = Literal["public", "auth", "admin"]


@dataclass(frozen=True)
class RateLimitConfig:
    enabled: bool
    public_per_minute: int
    auth_per_minute: int
    admin_per_minute: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    bucket: Bucket
    limit: int
    remaining: int
    reset_seconds: int
    identity: str


class MemoryRateLimitStore:
    """Process-local fixed-window counters for tests and Redis outages."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[int, int]] = {}

    def incr(self, key: str, *, window_seconds: int = 60) -> tuple[int, int]:
        now = int(time.time())
        window_start = now - (now % window_seconds)
        with self._lock:
            count, start = self._windows.get(key, (0, window_start))
            if start != window_start:
                count, start = 0, window_start
            count += 1
            self._windows[key] = (count, start)
            reset = window_seconds - (now - window_start)
            return count, max(reset, 0)


class RedisRateLimitStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def incr(self, key: str, *, window_seconds: int = 60) -> tuple[int, int]:
        count = int(self._client.incr(key))
        if count == 1:
            self._client.expire(key, window_seconds)
        ttl = int(self._client.ttl(key))
        if ttl < 0:
            ttl = window_seconds
        return count, ttl


class RateLimiter:
    def __init__(
        self,
        config: RateLimitConfig,
        store: MemoryRateLimitStore | RedisRateLimitStore,
        *,
        store_name: str,
    ) -> None:
        self.config = config
        self._store = store
        self.store_name = store_name

    def limit_for(self, bucket: Bucket) -> int:
        if bucket == "admin":
            return self.config.admin_per_minute
        if bucket == "auth":
            return self.config.auth_per_minute
        return self.config.public_per_minute

    def check(self, bucket: Bucket, identity: str) -> RateLimitDecision:
        limit = self.limit_for(bucket)
        if not self.config.enabled or limit <= 0:
            return RateLimitDecision(
                allowed=True,
                bucket=bucket,
                limit=limit,
                remaining=limit,
                reset_seconds=60,
                identity=identity,
            )
        key = f"rl:{bucket}:{identity}"
        count, reset = self._store.incr(key, window_seconds=60)
        remaining = max(limit - count, 0)
        return RateLimitDecision(
            allowed=count <= limit,
            bucket=bucket,
            limit=limit,
            remaining=remaining,
            reset_seconds=reset,
            identity=identity,
        )

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.config.enabled,
            "store": self.store_name,
            "public_per_minute": self.config.public_per_minute,
            "auth_per_minute": self.config.auth_per_minute,
            "admin_per_minute": self.config.admin_per_minute,
            "window_seconds": 60,
        }


_limiter: RateLimiter | None = None
_limiter_key: tuple[object, ...] | None = None
_limiter_lock = threading.Lock()


def build_rate_limiter(
    *,
    enabled: bool,
    public_per_minute: int,
    auth_per_minute: int,
    admin_per_minute: int,
    redis_url: str,
) -> RateLimiter:
    config = RateLimitConfig(
        enabled=enabled,
        public_per_minute=public_per_minute,
        auth_per_minute=auth_per_minute,
        admin_per_minute=admin_per_minute,
    )
    client = create_redis_client(redis_url) if enabled else None
    if client is not None:
        return RateLimiter(config, RedisRateLimitStore(client), store_name="redis")
    if enabled:
        logger.warning("Rate limit enabled but Redis unavailable; using memory store")
    return RateLimiter(config, MemoryRateLimitStore(), store_name="memory")


def get_rate_limiter(
    *,
    enabled: bool,
    public_per_minute: int,
    auth_per_minute: int,
    admin_per_minute: int,
    redis_url: str,
) -> RateLimiter:
    global _limiter, _limiter_key
    key = (enabled, public_per_minute, auth_per_minute, admin_per_minute, redis_url)
    with _limiter_lock:
        if _limiter is None or _limiter_key != key:
            _limiter = build_rate_limiter(
                enabled=enabled,
                public_per_minute=public_per_minute,
                auth_per_minute=auth_per_minute,
                admin_per_minute=admin_per_minute,
                redis_url=redis_url,
            )
            _limiter_key = key
        return _limiter


def reset_rate_limiter_for_tests() -> None:
    global _limiter, _limiter_key
    with _limiter_lock:
        _limiter = None
        _limiter_key = None
