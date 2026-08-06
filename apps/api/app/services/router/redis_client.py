"""Shared Redis client helper for Gate 6B router cache/metrics."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_redis_client(redis_url: str) -> Any | None:
    try:
        import redis
    except ImportError:
        logger.warning("redis package unavailable; AI router cache/metrics use memory")
        return None
    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable for AI router (%s)", exc.__class__.__name__)
        return None
