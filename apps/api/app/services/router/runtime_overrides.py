"""Process-wide router runtime overrides (Gate 10E)."""

from __future__ import annotations

_cache_ttl_seconds: int | None = None


def set_cache_ttl_seconds(ttl_seconds: int) -> int:
    global _cache_ttl_seconds
    _cache_ttl_seconds = max(1, int(ttl_seconds))
    return _cache_ttl_seconds


def clear_cache_ttl_seconds() -> None:
    global _cache_ttl_seconds
    _cache_ttl_seconds = None


def effective_cache_ttl_seconds(default: int) -> int:
    if _cache_ttl_seconds is not None:
        return _cache_ttl_seconds
    return max(1, int(default))
