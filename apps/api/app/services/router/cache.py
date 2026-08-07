"""Redis-backed intent cache for Gate 6B AI router."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class CacheClient(Protocol):
    def get(self, key: str) -> str | None: ...

    def setex(self, key: str, time: int, value: str) -> Any: ...


class RouterIntentCache:
    def __init__(
        self,
        client: CacheClient | None,
        *,
        enabled: bool,
        ttl_seconds: int,
        key_prefix: str = "ai_router:intent:",
    ) -> None:
        self._client = client
        self._enabled = enabled and client is not None
        self._ttl_seconds = max(1, ttl_seconds)
        self._key_prefix = key_prefix

    @property
    def enabled(self) -> bool:
        return self._enabled

    def make_key(self, *, query_text: str, market: str, intent_type: str) -> str:
        digest = hashlib.sha256(
            f"{market}|{intent_type}|{query_text.strip().lower()}".encode()
        ).hexdigest()
        return f"{self._key_prefix}{digest}"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self._enabled or self._client is None:
            return None
        try:
            raw = self._client.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI router cache get failed (%s)", exc.__class__.__name__)
            return None
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self._enabled or self._client is None:
            return
        try:
            from app.services.router.runtime_overrides import effective_cache_ttl_seconds

            ttl = effective_cache_ttl_seconds(self._ttl_seconds)
            self._client.setex(key, ttl, json.dumps(value, sort_keys=True))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI router cache set failed (%s)", exc.__class__.__name__)

    def set_ttl_seconds(self, ttl_seconds: int) -> int:
        self._ttl_seconds = max(1, int(ttl_seconds))
        return self._ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        from app.services.router.runtime_overrides import effective_cache_ttl_seconds

        return effective_cache_ttl_seconds(self._ttl_seconds)
