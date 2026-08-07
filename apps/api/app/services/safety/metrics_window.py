"""In-process sliding window for Gate 10E safety metrics."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowSnapshot:
    requests: int
    errors_5xx: int
    successes: int
    cost_usd: float
    latency_p95_ms: float
    latency_avg_ms: float
    window_seconds: int
    error_rate: float
    success_rate: float
    cost_usd_per_min: float


@dataclass
class _Sample:
    ts: float
    status_code: int
    latency_ms: float
    cost_usd: float
    success: bool


class MetricsWindow:
    """Ring of recent request samples used by kill switch / auto-tune."""

    def __init__(self, window_seconds: int = 300, max_samples: int = 10_000) -> None:
        self._window_seconds = max(30, int(window_seconds))
        self._max_samples = max(100, int(max_samples))
        self._lock = threading.Lock()
        self._samples: deque[_Sample] = deque()

    def configure(self, *, window_seconds: int | None = None) -> None:
        if window_seconds is not None:
            self._window_seconds = max(30, int(window_seconds))

    def record(
        self,
        *,
        status_code: int,
        latency_ms: float,
        cost_usd: float = 0.0,
        success: bool | None = None,
    ) -> None:
        now = time.time()
        ok = (200 <= status_code < 400) if success is None else success
        sample = _Sample(
            ts=now,
            status_code=int(status_code),
            latency_ms=max(0.0, float(latency_ms)),
            cost_usd=max(0.0, float(cost_usd)),
            success=bool(ok),
        )
        with self._lock:
            self._samples.append(sample)
            self._trim_locked(now)

    def snapshot(self) -> WindowSnapshot:
        now = time.time()
        with self._lock:
            self._trim_locked(now)
            samples = list(self._samples)
        requests = len(samples)
        errors = sum(1 for s in samples if s.status_code >= 500)
        successes = sum(1 for s in samples if s.success)
        cost = sum(s.cost_usd for s in samples)
        latencies = sorted(s.latency_ms for s in samples)
        if latencies:
            idx = min(len(latencies) - 1, max(0, int(round(0.95 * (len(latencies) - 1)))))
            p95 = latencies[idx]
            avg = sum(latencies) / len(latencies)
        else:
            p95 = 0.0
            avg = 0.0
        minutes = max(self._window_seconds / 60.0, 1e-6)
        return WindowSnapshot(
            requests=requests,
            errors_5xx=errors,
            successes=successes,
            cost_usd=cost,
            latency_p95_ms=p95,
            latency_avg_ms=avg,
            window_seconds=self._window_seconds,
            error_rate=(errors / requests) if requests else 0.0,
            success_rate=(successes / requests) if requests else 0.0,
            cost_usd_per_min=cost / minutes,
        )

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()

    def _trim_locked(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._samples and self._samples[0].ts < cutoff:
            self._samples.popleft()
        while len(self._samples) > self._max_samples:
            self._samples.popleft()
