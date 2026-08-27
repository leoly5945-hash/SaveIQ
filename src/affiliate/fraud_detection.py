"""Affiliate fraud detection for the Dealhunter AI Router.

Flags click fraud, attribution fraud, and rate-limit abuse before a routing
decision is made or a conversion is credited, and lets admins block/unblock
affiliate partners. MVP storage is in-memory with TTL-based eviction; every
store here (blocked partners as a hash, click/request counters as
sliding-window lists, fraud events as a capped log) maps directly onto
Redis primitives (HSET+EXPIRE, sliding-window sorted sets, a capped list) if
this needs to scale past a single process.

Gated by the `FEATURE_FRAUD_DETECTION` environment variable (default:
disabled). When disabled, `is_fraudulent` and `check_fraud_conversion`
always return False and no events/alerts are recorded - `block_partner`/
`unblock_partner` remain available as explicit admin actions regardless.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from prometheus_client import Counter, Gauge
from pydantic import BaseModel
from pydantic import Field as PydanticField

# requests is optional (webhook alerts only); imported lazily in _send_alert.

# ---------------------------------------------------------------------------
# Metrics (Prometheus, consistent with apps/api/app/observability/metrics.py)
# ---------------------------------------------------------------------------

FRAUD_CHECKS_TOTAL = Counter(
    "fraud_checks_total",
    "Fraud checks performed",
    ["check_type", "result"],  # check_type: routing|conversion, result: clean|flagged
)
FRAUD_EVENTS_TOTAL = Counter(
    "fraud_events_total",
    "Fraud events detected, by type",
    ["fraud_type"],
)
FRAUD_BLOCKED_PARTNERS = Gauge(
    "fraud_blocked_partners",
    "Currently blocked affiliate partner count",
)


def _feature_enabled(env_var: str = "FEATURE_FRAUD_DETECTION") -> bool:
    return os.getenv(env_var, "false").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_ip_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def _build_file_logger(artifacts_dir: Path, *, enabled: bool = True) -> logging.Logger:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    logger = logging.getLogger(f"dealhunter.affiliate.fraud_detection.{stamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler: logging.Handler
        if enabled:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(artifacts_dir / f"fraud_{stamp}.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
        else:
            # Disabled: no artifacts file, and hot-path log calls become no-ops.
            handler = logging.NullHandler()
        logger.addHandler(handler)
    return logger


@dataclass
class FraudEvent:
    """A single fraud signal raised by a check."""

    fraud_type: str
    affiliate_id: str
    user_id: str | None
    ip: str | None
    detail: str
    timestamp: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "fraud_type": self.fraud_type,
            "affiliate_id": self.affiliate_id,
            "user_id": self.user_id,
            "ip": self.ip,
            "detail": self.detail,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BlockRecord:
    """A partner block, optionally time-limited."""

    affiliate_id: str
    reason: str
    blocked_at: datetime
    expires_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "affiliate_id": self.affiliate_id,
            "reason": self.reason,
            "blocked_at": self.blocked_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class _Stats:
    routing_checks: int = 0
    routing_flagged: int = 0
    conversion_checks: int = 0
    conversion_flagged: int = 0
    events_by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class FraudDetector:
    """Detects affiliate click/attribution fraud and enforces partner blocks.

    Not process-shared: create one instance per API process (e.g. as a
    FastAPI app-state singleton). All thresholds are read from environment
    variables at construction time.
    """

    def __init__(
        self,
        *,
        artifacts_dir: str | Path = "artifacts",
        enabled: bool | None = None,
    ) -> None:
        self.enabled = _feature_enabled() if enabled is None else enabled

        self.click_rate_limit = _env_int("FRAUD_CLICK_RATE_LIMIT", 100)
        self.daily_click_limit = _env_int("FRAUD_DAILY_CLICK_LIMIT", 500)
        self.affiliate_rate_limit = _env_int("FRAUD_AFFILIATE_RATE_LIMIT", 1000)
        self.user_rate_limit = _env_int("FRAUD_USER_RATE_LIMIT", 100)
        self.velocity_window_minutes = _env_int("FRAUD_VELOCITY_WINDOW_MINUTES", 5)
        self.velocity_multiplier = _env_float("FRAUD_VELOCITY_MULTIPLIER", 3.0)
        self.click_lookback_hours = _env_int("FRAUD_CLICK_LOOKBACK_HOURS", 24)
        self.event_ttl_hours = _env_int("FRAUD_EVENT_TTL_HOURS", 24)
        self.ip_blacklist = _env_ip_set("FRAUD_IP_BLACKLIST")
        self.alert_webhook_url = os.getenv("FRAUD_ALERT_WEBHOOK_URL") or None

        self._lock = threading.RLock()
        self._blocked: dict[str, BlockRecord] = {}
        self._clicks_by_ip: dict[str, deque[datetime]] = defaultdict(deque)
        self._clicks_by_affiliate: dict[str, deque[datetime]] = defaultdict(deque)
        self._requests_by_user: dict[str, deque[datetime]] = defaultdict(deque)
        self._click_pairs: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)
        self._conversions_by_user: dict[str, deque[datetime]] = defaultdict(deque)
        self._events: deque[FraudEvent] = deque()
        self._stats = _Stats()

        self._logger = _build_file_logger(Path(artifacts_dir), enabled=self.enabled)
        self._logger.info(
            json.dumps(
                {
                    "event": "detector_initialized",
                    "enabled": self.enabled,
                    "click_rate_limit": self.click_rate_limit,
                    "daily_click_limit": self.daily_click_limit,
                    "affiliate_rate_limit": self.affiliate_rate_limit,
                    "user_rate_limit": self.user_rate_limit,
                    "ip_blacklist_size": len(self.ip_blacklist),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _prune(timestamps: deque[datetime], cutoff: datetime) -> None:
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    def _prune_events(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=self.event_ttl_hours)
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def _is_velocity_abnormal(self, affiliate_id: str, now: datetime) -> bool:
        timestamps = self._clicks_by_affiliate.get(affiliate_id, deque())
        recent_cutoff = now - timedelta(minutes=self.velocity_window_minutes)
        baseline_cutoff = now - timedelta(minutes=60)
        baseline_minutes = 60 - self.velocity_window_minutes
        if baseline_minutes <= 0:
            return False

        recent_count = sum(1 for t in timestamps if t >= recent_cutoff)
        baseline_count = sum(1 for t in timestamps if baseline_cutoff <= t < recent_cutoff)
        # Require a minimum baseline sample so a cold start doesn't read as a spike.
        if baseline_count < 3:
            return False

        recent_rate = recent_count / self.velocity_window_minutes
        baseline_rate = baseline_count / baseline_minutes
        if baseline_rate <= 0:
            return False
        return recent_rate > baseline_rate * self.velocity_multiplier

    def _record_event(
        self,
        fraud_type: str,
        *,
        affiliate_id: str,
        user_id: str | None,
        ip: str | None,
        detail: str,
        now: datetime,
    ) -> FraudEvent:
        fraud_event = FraudEvent(
            fraud_type=fraud_type,
            affiliate_id=affiliate_id,
            user_id=user_id,
            ip=ip,
            detail=detail,
            timestamp=now,
        )
        with self._lock:
            self._events.append(fraud_event)
            self._stats.events_by_type[fraud_type] += 1
        FRAUD_EVENTS_TOTAL.labels(fraud_type=fraud_type).inc()
        self._logger.warning(json.dumps({"event": "fraud_detected", **fraud_event.as_dict()}))
        self._send_alert(fraud_event)
        return fraud_event

    def _send_alert(self, fraud_event: FraudEvent) -> None:
        webhook_url = self.alert_webhook_url
        if not webhook_url:
            return

        def _post() -> None:
            try:
                import requests
            except ImportError:
                self._logger.warning(
                    json.dumps(
                        {"event": "alert_webhook_skipped", "reason": "requests_not_installed"}
                    )
                )
                return
            try:
                requests.post(webhook_url, json=fraud_event.as_dict(), timeout=3)
            except requests.RequestException as exc:
                self._logger.warning(
                    json.dumps({"event": "alert_webhook_failed", "error": str(exc)})
                )

        threading.Thread(target=_post, daemon=True).start()

    # -- fraud checks ---------------------------------------------------------

    def is_fraudulent(self, affiliate_id: str, user_id: str, ip: str) -> bool:
        """Check click fraud / rate limits / blocks before routing a request.

        Returns False unconditionally when `FEATURE_FRAUD_DETECTION` is
        disabled, so callers can invoke this unconditionally before routing.
        """
        if not self.enabled:
            return False

        now = datetime.now(UTC)
        reasons: list[str] = []

        with self._lock:
            self._prune_events(now)

            if self._is_blocked_locked(affiliate_id, now):
                reasons.append("partner_blocked")
            if ip in self.ip_blacklist:
                reasons.append("ip_blacklisted")

            ip_clicks = self._clicks_by_ip[ip]
            ip_clicks.append(now)
            self._prune(ip_clicks, now - timedelta(hours=1))
            if len(ip_clicks) > self.click_rate_limit:
                reasons.append("ip_click_rate_exceeded")

            affiliate_clicks = self._clicks_by_affiliate[affiliate_id]
            affiliate_clicks.append(now)
            self._prune(affiliate_clicks, now - timedelta(hours=24))
            daily_count = len(affiliate_clicks)
            hourly_count = sum(1 for t in affiliate_clicks if t >= now - timedelta(hours=1))
            if daily_count > self.daily_click_limit:
                reasons.append("affiliate_daily_click_limit_exceeded")
            if hourly_count > self.affiliate_rate_limit:
                reasons.append("affiliate_rate_limit_exceeded")
            if self._is_velocity_abnormal(affiliate_id, now):
                reasons.append("abnormal_click_velocity")

            user_requests = self._requests_by_user[user_id]
            user_requests.append(now)
            self._prune(user_requests, now - timedelta(hours=1))
            if len(user_requests) > self.user_rate_limit:
                reasons.append("user_rate_limit_exceeded")

            click_pair = self._click_pairs[(affiliate_id, user_id)]
            click_pair.append(now)
            self._prune(click_pair, now - timedelta(hours=self.click_lookback_hours))

            self._stats.routing_checks += 1
            if reasons:
                self._stats.routing_flagged += 1

        FRAUD_CHECKS_TOTAL.labels(
            check_type="routing", result="flagged" if reasons else "clean"
        ).inc()

        for reason in reasons:
            self._record_event(
                reason,
                affiliate_id=affiliate_id,
                user_id=user_id,
                ip=ip,
                detail=f"is_fraudulent flagged: {reason}",
                now=now,
            )
        return bool(reasons)

    def check_fraud_conversion(
        self,
        affiliate_id: str,
        user_id: str,
        conversion_id: str | None = None,
        *,
        ip: str | None = None,
    ) -> bool:
        """Check a conversion for attribution fraud after it is recorded.

        Returns False unconditionally when `FEATURE_FRAUD_DETECTION` is
        disabled.
        """
        if not self.enabled:
            return False

        now = datetime.now(UTC)
        reasons: list[str] = []

        with self._lock:
            self._prune_events(now)

            if ip is not None and ip in self.ip_blacklist:
                reasons.append("ip_blacklisted")

            click_pair = self._click_pairs.get((affiliate_id, user_id), deque())
            self._prune(click_pair, now - timedelta(hours=self.click_lookback_hours))
            if not click_pair:
                reasons.append("conversion_without_click")

            recent_conversions = self._conversions_by_user[user_id]
            self._prune(recent_conversions, now - timedelta(hours=max(1, self.event_ttl_hours)))
            has_recent_conversion = any(t >= now - timedelta(hours=1) for t in recent_conversions)
            if has_recent_conversion:
                reasons.append("rapid_repeat_conversion")

            recent_conversions.append(now)
            self._stats.conversion_checks += 1
            if reasons:
                self._stats.conversion_flagged += 1

        FRAUD_CHECKS_TOTAL.labels(
            check_type="conversion", result="flagged" if reasons else "clean"
        ).inc()

        for reason in reasons:
            self._record_event(
                reason,
                affiliate_id=affiliate_id,
                user_id=user_id,
                ip=ip,
                detail=f"check_fraud_conversion flagged: {reason} (conversion_id={conversion_id})",
                now=now,
            )
        return bool(reasons)

    # -- partner blocking -----------------------------------------------------

    def _is_blocked_locked(self, affiliate_id: str, now: datetime) -> bool:
        """Caller must hold `self._lock`."""
        record = self._blocked.get(affiliate_id)
        if record is None:
            return False
        if record.expires_at is not None and now >= record.expires_at:
            del self._blocked[affiliate_id]
            return False
        return True

    def block_partner(
        self, affiliate_id: str, reason: str, duration_hours: float | None = None
    ) -> BlockRecord:
        """Block an affiliate partner from routing, optionally for a fixed duration."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=duration_hours) if duration_hours else None
        record = BlockRecord(
            affiliate_id=affiliate_id, reason=reason, blocked_at=now, expires_at=expires_at
        )
        with self._lock:
            self._blocked[affiliate_id] = record
            blocked_count = len(self._blocked)
        FRAUD_BLOCKED_PARTNERS.set(blocked_count)
        self._logger.warning(json.dumps({"event": "partner_blocked", **record.as_dict()}))
        return record

    def unblock_partner(self, affiliate_id: str) -> bool:
        """Re-enable routing for a previously blocked partner. Returns True if it was blocked."""
        with self._lock:
            existed = self._blocked.pop(affiliate_id, None) is not None
            blocked_count = len(self._blocked)
        FRAUD_BLOCKED_PARTNERS.set(blocked_count)
        self._logger.info(
            json.dumps(
                {
                    "event": "partner_unblocked",
                    "affiliate_id": affiliate_id,
                    "was_blocked": existed,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )
        return existed

    def is_blocked(self, affiliate_id: str) -> bool:
        with self._lock:
            return self._is_blocked_locked(affiliate_id, datetime.now(UTC))

    # -- reporting --------------------------------------------------------------

    def get_status(self, *, recent_events_limit: int = 50) -> dict[str, Any]:
        """Blocked partners + recent fraud events, for GET /admin/fraud/status."""
        now = datetime.now(UTC)
        with self._lock:
            self._prune_events(now)
            active_blocks = [
                record.as_dict()
                for aff_id, record in self._blocked.items()
                if self._is_blocked_locked(aff_id, now)
            ]
            recent_events = [event.as_dict() for event in list(self._events)[-recent_events_limit:]]
        return {
            "enabled": self.enabled,
            "blocked_partners": active_blocks,
            "recent_fraud_events": recent_events,
        }

    def get_metrics(self) -> dict[str, Any]:
        """Fraud detection counters, for GET /admin/fraud/metrics."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "routing_checks": self._stats.routing_checks,
                "routing_flagged": self._stats.routing_flagged,
                "conversion_checks": self._stats.conversion_checks,
                "conversion_flagged": self._stats.conversion_flagged,
                "events_by_type": dict(self._stats.events_by_type),
                "blocked_partner_count": len(self._blocked),
                "thresholds": {
                    "click_rate_limit_per_hour": self.click_rate_limit,
                    "daily_click_limit": self.daily_click_limit,
                    "affiliate_rate_limit_per_hour": self.affiliate_rate_limit,
                    "user_rate_limit_per_hour": self.user_rate_limit,
                    "velocity_window_minutes": self.velocity_window_minutes,
                    "velocity_multiplier": self.velocity_multiplier,
                },
            }


# ---------------------------------------------------------------------------
# Admin API: fraud status, block/unblock, metrics.
#
# Standalone router kept decoupled from apps/api/app's auth stack (this
# module lives outside that package); it reuses the same ADMIN_API_TOKEN
# convention as apps/api/app/core/settings.py. Mount it with:
#     app.include_router(fraud_detection.router)
# ---------------------------------------------------------------------------

_default_detector = FraudDetector()


def get_detector() -> FraudDetector:
    """Process-wide detector instance used by the admin router."""
    return _default_detector


async def _require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = os.getenv("ADMIN_API_TOKEN", "dev-admin-token")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


class BlockPartnerPayload(BaseModel):
    affiliate_id: str
    reason: str
    duration_hours: float | None = PydanticField(default=None, gt=0)


class UnblockPartnerPayload(BaseModel):
    affiliate_id: str


router = APIRouter(
    prefix="/admin/fraud",
    tags=["admin-fraud"],
    dependencies=[Depends(_require_admin_token)],
)


@router.get("/status")
def get_fraud_status(detector: FraudDetector = Depends(get_detector)) -> dict[str, Any]:
    return detector.get_status()


@router.post("/block")
def block_partner_endpoint(
    payload: BlockPartnerPayload,
    detector: FraudDetector = Depends(get_detector),
) -> dict[str, Any]:
    record = detector.block_partner(payload.affiliate_id, payload.reason, payload.duration_hours)
    return {"blocked": record.as_dict()}


@router.post("/unblock")
def unblock_partner_endpoint(
    payload: UnblockPartnerPayload,
    detector: FraudDetector = Depends(get_detector),
) -> dict[str, Any]:
    existed = detector.unblock_partner(payload.affiliate_id)
    return {"affiliate_id": payload.affiliate_id, "was_blocked": existed}


@router.get("/metrics")
def get_fraud_metrics(detector: FraudDetector = Depends(get_detector)) -> dict[str, Any]:
    return detector.get_metrics()
