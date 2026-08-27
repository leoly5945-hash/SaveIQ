"""Affiliate attribution tracking for the Dealhunter AI Router.

Records every affiliate touchpoint produced by a routing decision and
attributes conversions back to affiliates using a configurable multi-touch
model (last-click, first-click, linear). MVP storage is in-memory; see
`SUGGESTED_TIMESCALEDB_SCHEMA` below for the persistence path once this
graduates out of the router prototype.

Gated by the `FEATURE_ATTRIBUTION` environment variable (default: disabled).
When disabled, tracking calls are no-ops so the router can call
`track_affiliate()` unconditionally on every decision.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from prometheus_client import Counter

# ---------------------------------------------------------------------------
# Metrics (Prometheus, consistent with apps/api/app/observability/metrics.py)
# ---------------------------------------------------------------------------

ATTRIBUTION_CONVERSIONS_TOTAL = Counter(
    "attribution_conversions_total",
    "Affiliate conversions credited via attribution (fractional under multi-touch models)",
    ["affiliate_id", "attribution_model"],
)
ATTRIBUTION_REVENUE_TOTAL = Counter(
    "attribution_revenue_total",
    "Revenue (USD) attributed to an affiliate via the active attribution model",
    ["affiliate_id", "attribution_model"],
)


class ConversionStatus(StrEnum):
    """Lifecycle state of a tracked affiliate touchpoint."""

    PENDING = "pending"
    CONVERTED = "converted"
    REJECTED = "rejected"


class AttributionModel(StrEnum):
    """Supported multi-touch attribution models."""

    LAST_CLICK = "last-click"
    FIRST_CLICK = "first-click"
    LINEAR = "linear"


@dataclass
class Touch:
    """A single routing decision that pointed a user at an affiliate."""

    user_id: str
    affiliate_id: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    status: ConversionStatus = ConversionStatus.PENDING


@dataclass
class ConversionRecord:
    """A resolved outcome (converted or rejected) for a user's touch chain."""

    user_id: str
    timestamp: datetime
    status: ConversionStatus
    revenue: float
    attribution_model: AttributionModel
    credited_affiliates: dict[str, float]


@dataclass
class AttributionReport:
    """Result of `AttributionTracker.get_attribution_report`."""

    partner_id: str
    start_date: date
    end_date: date
    attribution_model: AttributionModel
    conversion_count: int
    revenue: float
    attribution_credit: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "partner_id": self.partner_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "attribution_model": self.attribution_model.value,
            "conversion_count": self.conversion_count,
            "revenue": round(self.revenue, 2),
            "attribution_credit": round(self.attribution_credit, 4),
        }


def _feature_enabled(env_var: str = "FEATURE_ATTRIBUTION") -> bool:
    return os.getenv(env_var, "false").strip().lower() in {"1", "true", "yes", "on"}


def _build_file_logger(artifacts_dir: Path, *, enabled: bool = True) -> logging.Logger:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    logger = logging.getLogger(f"dealhunter.affiliate.attribution.{stamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler: logging.Handler
        if enabled:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(
                artifacts_dir / f"attribution_{stamp}.log", encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
        else:
            # Disabled: no artifacts file, and hot-path log calls become no-ops.
            handler = logging.NullHandler()
        logger.addHandler(handler)
    return logger


def _parse_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


class AttributionTracker:
    """In-memory affiliate attribution tracker for MVP use in the AI router.

    Not process-shared: create one instance per API process (e.g. as a
    FastAPI app-state singleton) and swap in a database-backed store using
    `SUGGESTED_TIMESCALEDB_SCHEMA` once volume outgrows a single process.
    """

    def __init__(
        self,
        attribution_model: AttributionModel = AttributionModel.LAST_CLICK,
        *,
        artifacts_dir: str | Path = "artifacts",
        enabled: bool | None = None,
    ) -> None:
        self.attribution_model = attribution_model
        self.enabled = _feature_enabled() if enabled is None else enabled
        self._lock = threading.Lock()
        self._touches: list[Touch] = []
        self._touches_by_user: dict[str, list[Touch]] = defaultdict(list)
        self._conversions: list[ConversionRecord] = []
        self._logger = _build_file_logger(Path(artifacts_dir), enabled=self.enabled)
        self._logger.info(
            json.dumps(
                {
                    "event": "tracker_initialized",
                    "attribution_model": attribution_model.value,
                    "enabled": self.enabled,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )

    def track_affiliate(
        self,
        user_id: str,
        affiliate_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Touch | None:
        """Record a routing decision that pointed `user_id` at `affiliate_id`.

        Safe to call unconditionally from the router: this is a no-op when
        `FEATURE_ATTRIBUTION` is disabled.
        """
        if not self.enabled:
            return None

        touch = Touch(
            user_id=user_id,
            affiliate_id=affiliate_id,
            timestamp=datetime.now(UTC),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._touches.append(touch)
            self._touches_by_user[user_id].append(touch)

        self._logger.info(
            json.dumps(
                {
                    "event": "touch",
                    "user_id": user_id,
                    "affiliate_id": affiliate_id,
                    "timestamp": touch.timestamp.isoformat(),
                    "metadata": touch.metadata,
                }
            )
        )
        return touch

    def record_conversion(
        self,
        user_id: str,
        revenue: float,
        *,
        timestamp: datetime | None = None,
    ) -> ConversionRecord | None:
        """Resolve `user_id`'s touch chain as a conversion and split credit."""
        return self._resolve(
            user_id,
            status=ConversionStatus.CONVERTED,
            revenue=revenue,
            timestamp=timestamp,
        )

    def record_rejection(
        self,
        user_id: str,
        *,
        timestamp: datetime | None = None,
    ) -> ConversionRecord | None:
        """Resolve `user_id`'s touch chain as rejected (e.g. fraud, refund)."""
        return self._resolve(
            user_id,
            status=ConversionStatus.REJECTED,
            revenue=0.0,
            timestamp=timestamp,
        )

    def _resolve(
        self,
        user_id: str,
        *,
        status: ConversionStatus,
        revenue: float,
        timestamp: datetime | None,
    ) -> ConversionRecord | None:
        if not self.enabled:
            return None

        with self._lock:
            chain = list(self._touches_by_user.get(user_id, []))
            if not chain:
                self._logger.info(
                    json.dumps({"event": "resolve_skipped_no_touches", "user_id": user_id})
                )
                return None

            credits = self._compute_credits(chain) if status == ConversionStatus.CONVERTED else {}
            for touch in chain:
                touch.status = status

            record = ConversionRecord(
                user_id=user_id,
                timestamp=timestamp or datetime.now(UTC),
                status=status,
                revenue=revenue,
                attribution_model=self.attribution_model,
                credited_affiliates=credits,
            )
            self._conversions.append(record)

        for affiliate_id, credit in credits.items():
            ATTRIBUTION_CONVERSIONS_TOTAL.labels(
                affiliate_id=affiliate_id, attribution_model=self.attribution_model.value
            ).inc(credit)
            ATTRIBUTION_REVENUE_TOTAL.labels(
                affiliate_id=affiliate_id, attribution_model=self.attribution_model.value
            ).inc(revenue * credit)

        self._logger.info(
            json.dumps(
                {
                    "event": "conversion_resolved",
                    "user_id": user_id,
                    "status": status.value,
                    "revenue": revenue,
                    "attribution_model": self.attribution_model.value,
                    "credited_affiliates": credits,
                    "timestamp": record.timestamp.isoformat(),
                }
            )
        )
        return record

    def _compute_credits(self, chain: list[Touch]) -> dict[str, float]:
        """Split attribution credit across a user's touch chain."""
        if self.attribution_model == AttributionModel.LAST_CLICK:
            return {chain[-1].affiliate_id: 1.0}
        if self.attribution_model == AttributionModel.FIRST_CLICK:
            return {chain[0].affiliate_id: 1.0}

        # linear: split equally across every touch, summing repeats per affiliate
        credits: dict[str, float] = defaultdict(float)
        share = 1.0 / len(chain)
        for touch in chain:
            credits[touch.affiliate_id] += share
        return dict(credits)

    def get_attribution_report(
        self,
        partner_id: str,
        start_date: str | date,
        end_date: str | date,
    ) -> AttributionReport:
        """Summarize a partner's conversions/revenue/credit over a date range."""
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        window_end_exclusive = datetime.combine(
            end + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
        window_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)

        with self._lock:
            conversions = list(self._conversions)

        conversion_count = 0
        revenue = 0.0
        attribution_credit = 0.0
        for record in conversions:
            if record.status != ConversionStatus.CONVERTED:
                continue
            if not (window_start <= record.timestamp < window_end_exclusive):
                continue
            credit = record.credited_affiliates.get(partner_id, 0.0)
            if credit <= 0.0:
                continue
            conversion_count += 1
            revenue += record.revenue * credit
            attribution_credit += credit

        return AttributionReport(
            partner_id=partner_id,
            start_date=start,
            end_date=end,
            attribution_model=self.attribution_model,
            conversion_count=conversion_count,
            revenue=revenue,
            attribution_credit=attribution_credit,
        )

    def get_conversion_rate(self, affiliate_id: str) -> float:
        """Return `affiliate_id`'s conversion rate as a percentage (0-100)."""
        with self._lock:
            touches = [t for t in self._touches if t.affiliate_id == affiliate_id]
            conversions = [
                r
                for r in self._conversions
                if r.status == ConversionStatus.CONVERTED
                and r.credited_affiliates.get(affiliate_id, 0.0) > 0.0
            ]

        if not touches:
            return 0.0
        return round(len(conversions) / len(touches) * 100, 2)

    def get_status(self) -> dict[str, Any]:
        """Touch/conversion counts and config, for GET /admin/attribution/status."""
        with self._lock:
            touch_count = len(self._touches)
            conversion_count = len(self._conversions)
        return {
            "enabled": self.enabled,
            "attribution_model": self.attribution_model.value,
            "touch_count": touch_count,
            "conversion_count": conversion_count,
        }


# ---------------------------------------------------------------------------
# Persistence path beyond MVP: PostgreSQL/TimescaleDB schema.
#
# The repo's apps/api already has an `affiliate_click_events` table and
# Alembic migrations (see apps/api/app/models, apps/api/alembic/versions) -
# when this module graduates past the router prototype, the tables below
# should be added there instead of re-implemented standalone.
# ---------------------------------------------------------------------------
SUGGESTED_TIMESCALEDB_SCHEMA = """
CREATE TABLE affiliate_touches (
    id              BIGSERIAL,
    user_id         TEXT NOT NULL,
    affiliate_id    TEXT NOT NULL,
    touched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|converted|rejected
    metadata        JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, touched_at)
);
SELECT create_hypertable('affiliate_touches', 'touched_at');
CREATE INDEX ON affiliate_touches (user_id, touched_at DESC);
CREATE INDEX ON affiliate_touches (affiliate_id, touched_at DESC);

CREATE TABLE affiliate_conversions (
    id                  BIGSERIAL,
    user_id             TEXT NOT NULL,
    resolved_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    status              TEXT NOT NULL,          -- converted|rejected
    revenue_usd         NUMERIC(12, 2) NOT NULL DEFAULT 0,
    attribution_model   TEXT NOT NULL,           -- last-click|first-click|linear
    credited_affiliates JSONB NOT NULL,          -- {"affiliate_id": credit_fraction}
    PRIMARY KEY (id, resolved_at)
);
SELECT create_hypertable('affiliate_conversions', 'resolved_at');
CREATE INDEX ON affiliate_conversions (user_id, resolved_at DESC);
"""

# ---------------------------------------------------------------------------
# Admin API: status + partner report.
#
# Mount with: app.include_router(attribution_tracking.router)
# (prefix is already /admin/attribution — do not add another /admin prefix)
# ---------------------------------------------------------------------------

_default_tracker = AttributionTracker()


def get_tracker() -> AttributionTracker:
    return _default_tracker


async def _require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = os.getenv("ADMIN_API_TOKEN", "dev-admin-token")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


router = APIRouter(
    prefix="/admin/attribution",
    tags=["admin-attribution"],
    dependencies=[Depends(_require_admin_token)],
)


@router.get("/status")
def get_attribution_status(tracker: AttributionTracker = Depends(get_tracker)) -> dict[str, Any]:
    return tracker.get_status()


@router.get("/report")
def get_partner_attribution_report(
    partner_id: str = Query(..., min_length=1),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    tracker: AttributionTracker = Depends(get_tracker),
) -> dict[str, Any]:
    return tracker.get_attribution_report(partner_id, start_date, end_date).as_dict()


@router.get("/conversion_rate")
def get_partner_conversion_rate(
    affiliate_id: str = Query(..., min_length=1),
    tracker: AttributionTracker = Depends(get_tracker),
) -> dict[str, Any]:
    return {
        "affiliate_id": affiliate_id,
        "conversion_rate_pct": tracker.get_conversion_rate(affiliate_id),
    }
