"""Lightweight per-endpoint fixed-window rate limiting (CP16).

Reuses the Redis / in-memory stores from :mod:`app.services.rate_limit`. Only
active when ``RATE_LIMIT_ENABLED`` is true (so local/tests are unaffected); it
protects the endpoints that spend provider tokens or send email.
"""

from __future__ import annotations

import threading

from app.core.settings import get_settings
from app.services.rate_limit import MemoryRateLimitStore, RedisRateLimitStore
from app.services.router.redis_client import create_redis_client

_memory_store = MemoryRateLimitStore()
_redis_store: RedisRateLimitStore | None = None
_redis_checked = False
_lock = threading.Lock()


def _store() -> MemoryRateLimitStore | RedisRateLimitStore:
    global _redis_store, _redis_checked
    if not _redis_checked:
        with _lock:
            if not _redis_checked:
                client = create_redis_client(get_settings().redis_url)
                _redis_store = RedisRateLimitStore(client) if client is not None else None
                _redis_checked = True
    return _redis_store or _memory_store


def allow(name: str, identity: str, *, per_minute: int) -> bool:
    """True if this call is within ``per_minute`` for ``(name, identity)``."""

    if per_minute <= 0 or not get_settings().rate_limit_enabled:
        return True
    count, _ = _store().incr(f"ep:{name}:{identity}", window_seconds=60)
    return count <= per_minute


def reset_for_tests() -> None:
    global _redis_store, _redis_checked
    with _lock:
        _redis_store = None
        _redis_checked = False
        _memory_store._windows.clear()
