"""Sticky hash-based canary assignment (Gate 10C)."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from app.core.settings import Settings

logger = logging.getLogger(__name__)

CANARY_FEATURES = ("router", "bandit", "personalization", "llm_cn")
CONFIG_KEY = "canary:config:v1"
STATS_KEY = "canary:stats:v1"
STICKY_TTL_SECONDS = 24 * 60 * 60


@dataclass
class CanaryConfig:
    enabled: bool = False
    percentage: int = 0
    features: list[str] = field(default_factory=lambda: list(CANARY_FEATURES))
    sticky_session: bool = True

    def normalized_features(self) -> list[str]:
        allowed = set(CANARY_FEATURES)
        out = [f for f in self.features if f in allowed]
        return out or list(CANARY_FEATURES)


class CanaryService:
    def __init__(self, settings: Settings, redis_client: Any | None = None) -> None:
        self._settings = settings
        self._redis = redis_client
        self._lock = threading.Lock()
        self._memory_config: CanaryConfig | None = None
        self._memory_sticky: dict[str, bool] = {}
        self._memory_stats: dict[str, int] = {
            "canary_assignments": 0,
            "control_assignments": 0,
            "evaluations": 0,
        }

    def bootstrap_config(self) -> CanaryConfig:
        raw_features = self._settings.canary_features
        features = [part.strip() for part in raw_features.split(",") if part.strip()]
        return CanaryConfig(
            enabled=self._settings.canary_enabled,
            percentage=max(0, min(100, self._settings.canary_percentage)),
            features=features or list(CANARY_FEATURES),
            sticky_session=self._settings.canary_sticky_session,
        )

    def get_config(self) -> CanaryConfig:
        if self._redis is not None:
            try:
                raw = self._redis.get(CONFIG_KEY)
                if raw:
                    data = json.loads(raw)
                    return CanaryConfig(
                        enabled=bool(data.get("enabled", False)),
                        percentage=max(0, min(100, int(data.get("percentage", 0)))),
                        features=list(data.get("features") or CANARY_FEATURES),
                        sticky_session=bool(data.get("sticky_session", True)),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canary config read failed (%s)", exc.__class__.__name__)
        with self._lock:
            if self._memory_config is not None:
                return self._memory_config
        return self.bootstrap_config()

    def set_config(
        self,
        *,
        enabled: bool | None = None,
        percentage: int | None = None,
        features: list[str] | None = None,
        sticky_session: bool | None = None,
    ) -> CanaryConfig:
        current = self.get_config()
        updated = CanaryConfig(
            enabled=current.enabled if enabled is None else enabled,
            percentage=(
                current.percentage if percentage is None else max(0, min(100, int(percentage)))
            ),
            features=current.features if features is None else features,
            sticky_session=(current.sticky_session if sticky_session is None else sticky_session),
        )
        updated.features = updated.normalized_features()
        payload = {
            "enabled": updated.enabled,
            "percentage": updated.percentage,
            "features": updated.features,
            "sticky_session": updated.sticky_session,
        }
        if self._redis is not None:
            try:
                self._redis.set(CONFIG_KEY, json.dumps(payload))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canary config write failed (%s)", exc.__class__.__name__)
        with self._lock:
            self._memory_config = updated
        return updated

    def identity_for(self, user_id: str | None, client_ip: str | None) -> str | None:
        if user_id:
            return f"user:{user_id}"
        if client_ip:
            return f"ip:{client_ip}"
        return None

    def bucket(self, identity: str, feature: str = "") -> int:
        material = f"{identity}:{feature}" if feature else identity
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100

    def is_canary(self, identity: str | None, feature: str) -> bool:
        config = self.get_config()
        if not config.enabled or config.percentage <= 0:
            return False
        if feature not in config.normalized_features():
            return False
        if not identity:
            return False

        sticky_key = f"canary:sticky:{feature}:{identity}"
        if config.sticky_session:
            cached = self._get_sticky(sticky_key)
            if cached is not None:
                return cached

        assigned = self.bucket(identity, feature) < config.percentage
        if config.sticky_session:
            self._set_sticky(sticky_key, assigned)
        return assigned

    def get_active_features(self, identity: str | None) -> list[str]:
        config = self.get_config()
        if not config.enabled:
            return []
        return [
            feature for feature in config.normalized_features() if self.is_canary(identity, feature)
        ]

    def cohort_for(self, identity: str | None) -> str:
        """Request cohort label for metrics: off | canary | control."""
        config = self.get_config()
        if not config.enabled:
            return "off"
        if not identity:
            return "control"
        # Cohort uses identity-only bucket so HTTP metrics stay stable across features.
        return "canary" if self.bucket(identity) < config.percentage else "control"

    def record_assignment(self, cohort: str) -> None:
        if cohort == "off":
            return
        field = "canary_assignments" if cohort == "canary" else "control_assignments"
        if self._redis is not None:
            try:
                self._redis.hincrby(STATS_KEY, field, 1)
                self._redis.hincrby(STATS_KEY, "evaluations", 1)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canary stats write failed (%s)", exc.__class__.__name__)
        with self._lock:
            self._memory_stats[field] = int(self._memory_stats.get(field, 0)) + 1
            self._memory_stats["evaluations"] = int(self._memory_stats.get("evaluations", 0)) + 1

    def stats(self) -> dict[str, Any]:
        config = self.get_config()
        stats = dict(self._memory_stats)
        if self._redis is not None:
            try:
                raw = self._redis.hgetall(STATS_KEY) or {}
                for key, value in raw.items():
                    stats[str(key)] = int(float(value))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canary stats read failed (%s)", exc.__class__.__name__)
        return {
            "config": {
                "enabled": config.enabled,
                "percentage": config.percentage,
                "features": config.normalized_features(),
                "sticky_session": config.sticky_session,
            },
            "assignments": {
                "canary": int(stats.get("canary_assignments", 0)),
                "control": int(stats.get("control_assignments", 0)),
                "evaluations": int(stats.get("evaluations", 0)),
            },
        }

    def _get_sticky(self, key: str) -> bool | None:
        if self._redis is not None:
            try:
                value = self._redis.get(key)
                if value is None:
                    return None
                return str(value) in {"1", "true", "True"}
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canary sticky read failed (%s)", exc.__class__.__name__)
        with self._lock:
            return self._memory_sticky.get(key)

    def _set_sticky(self, key: str, assigned: bool) -> None:
        if self._redis is not None:
            try:
                self._redis.setex(key, STICKY_TTL_SECONDS, "1" if assigned else "0")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canary sticky write failed (%s)", exc.__class__.__name__)
        with self._lock:
            self._memory_sticky[key] = assigned


_service: CanaryService | None = None
_service_lock = threading.Lock()


def build_canary_service(settings: Settings) -> CanaryService:
    global _service
    with _service_lock:
        if _service is None:
            # Lazy import avoids canary ↔ router package cycle via redis_client.
            from app.services.router.redis_client import create_redis_client

            client = create_redis_client(settings.redis_url)
            _service = CanaryService(settings, client)
        else:
            # Keep bootstrap env in sync when callers pass a fresh Settings (tests).
            _service._settings = settings
        return _service


def reset_canary_service_for_tests() -> None:
    global _service
    with _service_lock:
        if _service is not None:
            if _service._redis is not None:
                try:
                    _service._redis.delete(CONFIG_KEY)
                    _service._redis.delete(STATS_KEY)
                except Exception:  # noqa: BLE001
                    pass
            _service._memory_config = None
            _service._memory_sticky.clear()
        _service = None
