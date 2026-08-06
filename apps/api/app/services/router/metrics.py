"""Request/token/cost metrics for Gate 6B AI router (Redis or in-memory)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

METRICS_KEY = "ai_router:metrics:v1"
STRATEGY_KEY = "ai_router:strategy"


class MetricsStore(Protocol):
    def hgetall(self, name: str) -> dict[str, str]: ...

    def hincrby(self, name: str, key: str, amount: int) -> Any: ...

    def hincrbyfloat(self, name: str, key: str, amount: float) -> Any: ...

    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> Any: ...


@dataclass
class InMemoryMetricsStore:
    hashes: dict[str, dict[str, str]] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def hgetall(self, name: str) -> dict[str, str]:
        with self._lock:
            return dict(self.hashes.get(name, {}))

    def hincrby(self, name: str, key: str, amount: int) -> int:
        with self._lock:
            bucket = self.hashes.setdefault(name, {})
            current = int(float(bucket.get(key, "0")))
            current += amount
            bucket[key] = str(current)
            return current

    def hincrbyfloat(self, name: str, key: str, amount: float) -> float:
        with self._lock:
            bucket = self.hashes.setdefault(name, {})
            current = float(bucket.get(key, "0"))
            current += amount
            bucket[key] = str(current)
            return current

    def get(self, name: str) -> str | None:
        with self._lock:
            return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        with self._lock:
            self.values[name] = value


class RouterMetrics:
    def __init__(self, store: MetricsStore | None = None) -> None:
        self._store: MetricsStore = store or InMemoryMetricsStore()

    def record_request(
        self,
        *,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        estimated_cost_usd: float,
        latency_ms: float,
        error: bool = False,
        cache_hit: bool = False,
    ) -> None:
        try:
            prefix = f"provider:{provider}:"
            self._store.hincrby(METRICS_KEY, f"{prefix}requests", 1)
            self._store.hincrby(METRICS_KEY, f"{prefix}prompt_tokens", max(0, prompt_tokens))
            self._store.hincrby(
                METRICS_KEY, f"{prefix}completion_tokens", max(0, completion_tokens)
            )
            self._store.hincrbyfloat(
                METRICS_KEY, f"{prefix}estimated_cost_usd", max(0.0, estimated_cost_usd)
            )
            self._store.hincrbyfloat(METRICS_KEY, f"{prefix}latency_ms_total", max(0.0, latency_ms))
            if error:
                self._store.hincrby(METRICS_KEY, f"{prefix}errors", 1)
            if cache_hit:
                self._store.hincrby(METRICS_KEY, "cache_hits", 1)
            else:
                self._store.hincrby(METRICS_KEY, "cache_misses", 1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI router metrics record failed (%s)", exc.__class__.__name__)

    def snapshot(self) -> dict[str, Any]:
        try:
            raw = self._store.hgetall(METRICS_KEY)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI router metrics read failed (%s)", exc.__class__.__name__)
            raw = {}
        providers: dict[str, dict[str, float | int]] = {}
        for key, value in raw.items():
            if not key.startswith("provider:"):
                continue
            _, provider, metric = key.split(":", 2)
            bucket = providers.setdefault(
                provider,
                {
                    "requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "errors": 0,
                    "avg_latency_ms": 0.0,
                    "latency_ms_total": 0.0,
                },
            )
            if metric in {"estimated_cost_usd", "latency_ms_total"}:
                bucket[metric] = float(value)
            else:
                bucket[metric] = int(float(value))
        for bucket in providers.values():
            requests = int(bucket.get("requests", 0))
            total_latency = float(bucket.get("latency_ms_total", 0.0))
            bucket["avg_latency_ms"] = round(total_latency / requests, 3) if requests else 0.0
            bucket.pop("latency_ms_total", None)
            bucket["estimated_cost_usd"] = round(float(bucket.get("estimated_cost_usd", 0.0)), 8)
        return {
            "providers": providers,
            "cache_hits": int(float(raw.get("cache_hits", "0"))),
            "cache_misses": int(float(raw.get("cache_misses", "0"))),
        }

    def get_strategy_override(self) -> str | None:
        try:
            value = self._store.get(STRATEGY_KEY)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI router strategy read failed (%s)", exc.__class__.__name__)
            return None
        return value

    def set_strategy_override(self, strategy: str) -> None:
        try:
            self._store.set(STRATEGY_KEY, strategy)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI router strategy write failed (%s)", exc.__class__.__name__)
            raise
