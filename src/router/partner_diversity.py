"""Partner traffic diversity for the Dealhunter AI Router.

Takes bandit scores for affiliate partners and produces a traffic-share
weight distribution that stays close to the bandit's exploit preference
while (a) respecting min/max share constraints per partner and (b) holding
back an exploration budget for new or under-used partners, so the router
doesn't collapse onto a single "best" partner. MVP storage is in-memory;
swap in a DB/timeseries store for durable long-term Gini history if this
needs to survive process restarts.

Gated by the `FEATURE_PARTNER_DIVERSITY` environment variable (default:
disabled). When disabled, `apply_diversity_constraint` returns the input
`affiliate_scores` unchanged - no normalization, blending, or constraints.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from prometheus_client import Gauge
from pydantic import BaseModel
from pydantic import Field as PydanticField

# ---------------------------------------------------------------------------
# Metrics (Prometheus, consistent with apps/api/app/observability/metrics.py)
# ---------------------------------------------------------------------------

DIVERSITY_GINI = Gauge(
    "diversity_gini",
    "Gini coefficient of the current partner traffic-share distribution",
)
PARTNER_TRAFFIC_SHARE = Gauge(
    "partner_traffic_share",
    "Current traffic share allocated to an affiliate partner",
    ["affiliate_id"],
)
DIVERSITY_ACTIVE_PARTNERS = Gauge(
    "diversity_active_partners",
    "Number of partners considered in the last diversity computation",
)


def _feature_enabled(env_var: str = "FEATURE_PARTNER_DIVERSITY") -> bool:
    return os.getenv(env_var, "false").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _build_file_logger(artifacts_dir: Path, *, enabled: bool = True) -> logging.Logger:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    logger = logging.getLogger(f"dealhunter.router.partner_diversity.{stamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler: logging.Handler
        if enabled:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(
                artifacts_dir / f"diversity_{stamp}.log", encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
        else:
            # Disabled: no artifacts file, and hot-path log calls become no-ops.
            handler = logging.NullHandler()
        logger.addHandler(handler)
    return logger


_HISTORY_MAXLEN = 20_000


class DiversityManager:
    """Blends bandit scores with an exploration budget under share constraints.

    Not process-shared: create one instance per API process (e.g. as a
    FastAPI app-state singleton).
    """

    def __init__(
        self,
        *,
        artifacts_dir: str | Path = "artifacts",
        enabled: bool | None = None,
    ) -> None:
        self.enabled = _feature_enabled() if enabled is None else enabled
        self.max_partner_share = _env_float("DIVERSITY_MAX_PARTNER_SHARE", 0.5)
        self.min_partner_share = _env_float("DIVERSITY_MIN_PARTNER_SHARE", 0.05)
        self.epsilon = _env_float("DIVERSITY_EPSILON", 0.1)
        self.explore_days = _env_int("DIVERSITY_EXPLORE_DAYS", 7)

        self._lock = threading.RLock()
        self._partner_caps: dict[str, float] = {}
        self._first_seen: dict[str, datetime] = {}
        self._history: deque[tuple[datetime, float]] = deque(maxlen=_HISTORY_MAXLEN)
        self._last_weights: dict[str, float] = {}
        self._last_gini: float | None = None

        self._logger = _build_file_logger(Path(artifacts_dir), enabled=self.enabled)
        self._logger.info(
            json.dumps(
                {
                    "event": "manager_initialized",
                    "enabled": self.enabled,
                    "max_partner_share": self.max_partner_share,
                    "min_partner_share": self.min_partner_share,
                    "epsilon": self.epsilon,
                    "explore_days": self.explore_days,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )

    # -- Gini ---------------------------------------------------------------

    def calculate_gini(self, weights: Mapping[str, float] | Sequence[float]) -> float:
        """Gini coefficient of a set of weights (0 = equal, 1 = maximally unequal).

        `Gini = (sum_i sum_j |w_i - w_j|) / (2 * n * sum(w))`.
        """
        values = list(weights.values()) if isinstance(weights, Mapping) else list(weights)
        n = len(values)
        total = sum(values)
        if n == 0 or total <= 0:
            return 0.0
        abs_diff_sum = sum(abs(vi - vj) for vi in values for vj in values)
        return abs_diff_sum / (2 * n * total)

    def get_diversity_history(self, days: int = 30) -> list[tuple[datetime, float]]:
        """Recorded (timestamp, gini) snapshots from the last `days` days."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with self._lock:
            return [(ts, gini) for ts, gini in self._history if ts >= cutoff]

    # -- weight math ----------------------------------------------------------

    @staticmethod
    def _normalize(values: Mapping[str, float]) -> dict[str, float]:
        clipped = {k: max(0.0, v) for k, v in values.items()}
        total = sum(clipped.values())
        if total <= 0:
            n = len(clipped) or 1
            return dict.fromkeys(clipped, 1.0 / n)
        return {k: v / total for k, v in clipped.items()}

    def _is_new(self, affiliate_id: str, now: datetime) -> bool:
        first_seen = self._first_seen.get(affiliate_id)
        if first_seen is None:
            return True
        return now - first_seen <= timedelta(days=self.explore_days)

    def _explore_weights(self, partner_ids: list[str], now: datetime) -> dict[str, float]:
        new_partners = [pid for pid in partner_ids if self._is_new(pid, now)]
        pool = new_partners or partner_ids
        share = 1.0 / len(pool)
        return {pid: (share if pid in pool else 0.0) for pid in partner_ids}

    def _apply_bounds(self, weights: dict[str, float]) -> dict[str, float]:
        """Project `weights` (already summing to ~1.0) onto the [floor, cap] box per partner."""
        floors = dict.fromkeys(weights, self.min_partner_share)
        caps = {pid: self._partner_caps.get(pid, self.max_partner_share) for pid in weights}

        floor_total = sum(floors.values())
        if floor_total > 1.0:
            scale = 0.999 / floor_total
            floors = {pid: f * scale for pid, f in floors.items()}
        cap_total = sum(caps.values())
        if cap_total < 1.0:
            scale = 1.001 / cap_total
            caps = {pid: min(1.0, c * scale) for pid, c in caps.items()}

        fixed: dict[str, float] = {}
        free = set(weights.keys())
        remaining_total = 1.0

        for _ in range(len(weights) + 1):
            if not free:
                break
            free_raw_sum = sum(weights[pid] for pid in free)
            if free_raw_sum <= 0:
                alloc = {pid: remaining_total / len(free) for pid in free}
            else:
                alloc = {pid: remaining_total * weights[pid] / free_raw_sum for pid in free}

            violators = {
                pid: v for pid, v in alloc.items() if v > caps[pid] + 1e-9 or v < floors[pid] - 1e-9
            }
            if not violators:
                fixed.update(alloc)
                free.clear()
                break

            for pid, v in violators.items():
                bound = caps[pid] if v > caps[pid] else floors[pid]
                fixed[pid] = bound
                free.discard(pid)
                remaining_total -= bound
            remaining_total = max(0.0, remaining_total)

        for pid in free:  # pragma: no cover - safety net if iteration cap is hit
            fixed[pid] = remaining_total / max(1, len(free))

        return self._normalize(fixed)

    def apply_diversity_constraint(
        self,
        affiliate_scores: dict[str, float],
        partner_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Blend exploit (bandit scores) with an exploration budget, under share bounds.

        Called during routing. Returns `affiliate_scores` unchanged when
        `FEATURE_PARTNER_DIVERSITY` is disabled, so callers can invoke this
        unconditionally on the router's hot path.
        """
        if not self.enabled:
            return dict(affiliate_scores)
        if not affiliate_scores:
            return {}

        now = datetime.now(UTC)
        partner_ids = list(affiliate_scores.keys())

        with self._lock:
            for pid in partner_ids:
                self._first_seen.setdefault(pid, now)

            base = (
                {pid: partner_weights.get(pid, 0.0) for pid in partner_ids}
                if partner_weights is not None
                else dict(affiliate_scores)
            )
            exploit_weights = self._normalize(base)
            explore_weights = self._explore_weights(partner_ids, now)
            blended = {
                pid: (1 - self.epsilon) * exploit_weights[pid] + self.epsilon * explore_weights[pid]
                for pid in partner_ids
            }
            final_weights = self._apply_bounds(blended)
            gini = self.calculate_gini(final_weights)

            self._last_weights = dict(final_weights)
            self._last_gini = gini
            self._history.append((now, gini))

        DIVERSITY_GINI.set(gini)
        DIVERSITY_ACTIVE_PARTNERS.set(len(final_weights))
        for pid, share in final_weights.items():
            PARTNER_TRAFFIC_SHARE.labels(affiliate_id=pid).set(share)

        self._logger.info(
            json.dumps(
                {
                    "event": "diversity_applied",
                    "gini": round(gini, 4),
                    "weights": {k: round(v, 4) for k, v in final_weights.items()},
                    "timestamp": now.isoformat(),
                }
            )
        )
        return final_weights

    # -- partner caps -----------------------------------------------------------

    def set_partner_cap(self, affiliate_id: str, max_percentage: float) -> None:
        """Override the global max share for a specific partner (0 < max_percentage <= 1)."""
        if not (0.0 < max_percentage <= 1.0):
            raise ValueError("max_percentage must be in (0, 1]")
        with self._lock:
            self._partner_caps[affiliate_id] = max_percentage
        self._logger.info(
            json.dumps(
                {
                    "event": "partner_cap_set",
                    "affiliate_id": affiliate_id,
                    "max_percentage": max_percentage,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )

    def reset_to_defaults(self) -> int:
        """Clear all partner-specific caps, reverting everyone to the global bounds.

        Returns the number of caps that were cleared.
        """
        with self._lock:
            cleared = len(self._partner_caps)
            self._partner_caps.clear()
        self._logger.info(
            json.dumps(
                {
                    "event": "reset_to_defaults",
                    "caps_cleared": cleared,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )
        return cleared

    # -- reporting --------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Current Gini, partner shares, and active partners, for GET /admin/diversity/status."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "gini": round(self._last_gini, 4) if self._last_gini is not None else None,
                "partner_shares": {k: round(v, 4) for k, v in self._last_weights.items()},
                "active_partners": list(self._last_weights.keys()),
                "partner_caps": dict(self._partner_caps),
                "config": {
                    "max_partner_share": self.max_partner_share,
                    "min_partner_share": self.min_partner_share,
                    "epsilon": self.epsilon,
                    "explore_days": self.explore_days,
                },
            }


# ---------------------------------------------------------------------------
# Admin API: diversity status, partner caps, reset.
#
# Standalone router kept decoupled from apps/api/app's auth stack (this
# module lives outside that package); it reuses the same ADMIN_API_TOKEN
# convention as apps/api/app/core/settings.py. Mount it with:
#     app.include_router(partner_diversity.router)
# ---------------------------------------------------------------------------

_default_manager = DiversityManager()


def get_manager() -> DiversityManager:
    """Process-wide manager instance used by the admin router."""
    return _default_manager


async def _require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = os.getenv("ADMIN_API_TOKEN", "dev-admin-token")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


class SetPartnerCapPayload(BaseModel):
    affiliate_id: str
    max_percentage: float = PydanticField(gt=0, le=1)


router = APIRouter(
    prefix="/admin/diversity",
    tags=["admin-diversity"],
    dependencies=[Depends(_require_admin_token)],
)


@router.get("/status")
def get_diversity_status(manager: DiversityManager = Depends(get_manager)) -> dict[str, Any]:
    return manager.get_status()


@router.post("/cap")
def set_partner_cap_endpoint(
    payload: SetPartnerCapPayload,
    manager: DiversityManager = Depends(get_manager),
) -> dict[str, Any]:
    manager.set_partner_cap(payload.affiliate_id, payload.max_percentage)
    return {"affiliate_id": payload.affiliate_id, "max_percentage": payload.max_percentage}


@router.post("/reset")
def reset_diversity_endpoint(manager: DiversityManager = Depends(get_manager)) -> dict[str, Any]:
    cleared = manager.reset_to_defaults()
    return {"caps_cleared": cleared}
