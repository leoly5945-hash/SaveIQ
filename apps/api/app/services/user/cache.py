"""Redis / memory cache for anonymous user profiles."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProfileCache:
    def __init__(
        self,
        redis_client: Any | None,
        *,
        enabled: bool = True,
        ttl_seconds: int = 300,
        key_prefix: str = "personalization:profile:v1:",
    ) -> None:
        self._redis = redis_client
        self.enabled = enabled and redis_client is not None
        self.ttl_seconds = max(1, int(ttl_seconds))
        self._prefix = key_prefix
        self._memory: dict[str, str] = {}

    def get(self, user_id: str) -> dict[str, Any] | None:
        key = self._prefix + user_id
        raw: str | None
        client = self._redis
        if self.enabled and client is not None:
            try:
                raw = client.get(key)
            except Exception:  # noqa: BLE001
                logger.warning("Profile cache get failed; using memory")
                raw = self._memory.get(key)
        else:
            raw = self._memory.get(key)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def set(self, user_id: str, payload: dict[str, Any]) -> None:
        key = self._prefix + user_id
        raw = json.dumps(payload)
        self._memory[key] = raw
        client = self._redis
        if not self.enabled or client is None:
            return
        try:
            client.setex(key, self.ttl_seconds, raw)
        except Exception:  # noqa: BLE001
            logger.warning("Profile cache set failed; memory only")

    def delete(self, user_id: str) -> None:
        key = self._prefix + user_id
        self._memory.pop(key, None)
        client = self._redis
        if not self.enabled or client is None:
            return
        try:
            client.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning("Profile cache delete failed")
