"""Multi-objective scoring for the Dealhunter AI Router.

Combines conversion rate, revenue-per-user, and user satisfaction into a
single weighted score routing decisions can be ranked on, instead of
optimizing conversion rate alone.

Gated by the `FEATURE_MULTI_OBJECTIVE` environment variable (default:
disabled). When disabled, `calculate_score` falls back to returning the
raw, unweighted `conversion_rate` so callers can invoke it unconditionally.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from prometheus_client import Gauge, Histogram
from pydantic import BaseModel
from pydantic import Field as PydanticField

# ---------------------------------------------------------------------------
# Objective definitions
# ---------------------------------------------------------------------------

Objective = Literal["conversion_rate", "revenue_per_user", "user_satisfaction"]
NormalizationMode = Literal["minmax", "zscore"]

OBJECTIVES: tuple[Objective, ...] = ("conversion_rate", "revenue_per_user", "user_satisfaction")

# Known valid ranges, used by min-max normalization.
OBJECTIVE_BOUNDS: dict[Objective, tuple[float, float]] = {
    "conversion_rate": (0.0, 1.0),
    "revenue_per_user": (0.0, 100.0),
    "user_satisfaction": (1.0, 5.0),
}

DEFAULT_WEIGHTS: dict[Objective, float] = {
    "conversion_rate": 0.4,
    "revenue_per_user": 0.35,
    "user_satisfaction": 0.25,
}

_ENV_WEIGHT_VARS: dict[Objective, str] = {
    "conversion_rate": "OBJECTIVE_WEIGHT_CONVERSION_RATE",
    "revenue_per_user": "OBJECTIVE_WEIGHT_REVENUE_PER_USER",
    "user_satisfaction": "OBJECTIVE_WEIGHT_USER_SATISFACTION",
}

# ---------------------------------------------------------------------------
# Metrics (Prometheus, consistent with apps/api/app/observability/metrics.py)
# ---------------------------------------------------------------------------

OBJECTIVE_SCORE = Histogram(
    "objective_score",
    "Composite multi-objective routing score",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 2.0, 5.0),
)
OBJECTIVE_WEIGHTS = Gauge(
    "objective_weights",
    "Current weight assigned to each objective",
    ["objective"],
)


def _feature_enabled(env_var: str = "FEATURE_MULTI_OBJECTIVE") -> bool:
    return os.getenv(env_var, "false").strip().lower() in {"1", "true", "yes", "on"}


def _default_weights_from_env() -> dict[Objective, float]:
    weights: dict[Objective, float] = {}
    for objective in OBJECTIVES:
        raw = os.getenv(_ENV_WEIGHT_VARS[objective])
        weights[objective] = float(raw) if raw is not None else DEFAULT_WEIGHTS[objective]
    return _normalize_weights(weights)


def _normalize_weights(weights: dict[Objective, float]) -> dict[Objective, float]:
    total = sum(max(0.0, w) for w in weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {objective: max(0.0, w) / total for objective, w in weights.items()}


def _build_file_logger(artifacts_dir: Path, *, enabled: bool = True) -> logging.Logger:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    logger = logging.getLogger(f"dealhunter.router.multi_objective.{stamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler: logging.Handler
        if enabled:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(
                artifacts_dir / f"objective_{stamp}.log", encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
        else:
            # Disabled: no artifacts file, and hot-path log calls become no-ops.
            handler = logging.NullHandler()
        logger.addHandler(handler)
    return logger


@dataclass
class ObjectiveScore:
    """Full breakdown of a single scoring call."""

    raw: dict[Objective, float]
    normalized: dict[Objective, float]
    weights_used: dict[Objective, float]
    normalization: NormalizationMode
    total: float
    timestamp: datetime
    enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "normalized": {k: round(v, 4) for k, v in self.normalized.items()},
            "weights_used": {k: round(v, 4) for k, v in self.weights_used.items()},
            "normalization": self.normalization,
            "total": round(self.total, 4),
            "timestamp": self.timestamp.isoformat(),
            "enabled": self.enabled,
        }


@dataclass
class TradeoffAnalysis:
    """Elasticity of one objective with respect to another, from history."""

    objective_a: Objective
    objective_b: Objective
    sample_size: int
    correlation: float | None
    elasticity_pct: float | None
    interpretation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "objective_a": self.objective_a,
            "objective_b": self.objective_b,
            "sample_size": self.sample_size,
            "correlation": round(self.correlation, 4) if self.correlation is not None else None,
            "elasticity_pct": (
                round(self.elasticity_pct, 4) if self.elasticity_pct is not None else None
            ),
            "interpretation": self.interpretation,
        }


class ObjectiveOptimizer:
    """Weighted, multi-objective scorer for ranking routing decisions.

    Not process-shared: create one instance per API process (e.g. as a
    FastAPI app-state singleton). History is capped in-memory (`history_limit`)
    since this is an MVP scorer, not a durable analytics store.
    """

    def __init__(
        self,
        weights: dict[Objective, float] | None = None,
        *,
        normalization: NormalizationMode = "minmax",
        artifacts_dir: str | Path = "artifacts",
        history_limit: int = 10_000,
        enabled: bool | None = None,
    ) -> None:
        self.normalization = normalization
        self.enabled = _feature_enabled() if enabled is None else enabled
        self._lock = threading.Lock()
        self._weights: dict[Objective, float] = _normalize_weights(
            weights if weights is not None else _default_weights_from_env()
        )
        self._history: deque[dict[Objective, float]] = deque(maxlen=history_limit)
        self._logger = _build_file_logger(Path(artifacts_dir), enabled=self.enabled)
        self._publish_weight_metrics()
        self._logger.info(
            json.dumps(
                {
                    "event": "optimizer_initialized",
                    "weights": self._weights,
                    "normalization": self.normalization,
                    "enabled": self.enabled,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )

    def _publish_weight_metrics(self) -> None:
        for objective, weight in self._weights.items():
            OBJECTIVE_WEIGHTS.labels(objective=objective).set(weight)

    def get_weights(self) -> dict[Objective, float]:
        with self._lock:
            return dict(self._weights)

    def update_weights(self, weights: dict[str, float]) -> dict[Objective, float]:
        """Replace the active weights, auto-normalizing so they sum to 1.0."""
        missing = [o for o in OBJECTIVES if o not in weights]
        if missing:
            raise ValueError(f"Missing weight(s) for: {', '.join(missing)}")
        if any(weights[o] < 0 for o in OBJECTIVES):
            raise ValueError("Weights must be non-negative")

        normalized = _normalize_weights({o: float(weights[o]) for o in OBJECTIVES})
        with self._lock:
            self._weights = normalized
        self._publish_weight_metrics()
        self._logger.info(
            json.dumps(
                {
                    "event": "weights_updated",
                    "weights": normalized,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        )
        return normalized

    def _normalize_value(self, objective: Objective, value: float) -> float:
        if self.normalization == "minmax":
            lo, hi = OBJECTIVE_BOUNDS[objective]
            if hi <= lo:
                return 0.0
            return max(0.0, min(1.0, (value - lo) / (hi - lo)))

        # z-score: standardize against this objective's own history.
        samples = [h[objective] for h in self._history]
        if len(samples) < 2:
            lo, hi = OBJECTIVE_BOUNDS[objective]
            return max(0.0, min(1.0, (value - lo) / (hi - lo))) if hi > lo else 0.0
        mean = sum(samples) / len(samples)
        variance = sum((s - mean) ** 2 for s in samples) / len(samples)
        stddev = math.sqrt(variance)
        if stddev == 0:
            return 0.0
        return (value - mean) / stddev

    def get_score_breakdown(
        self,
        cr: float,
        rpu: float,
        us: float,
        weights: dict[Objective, float] | None = None,
    ) -> ObjectiveScore:
        """Return the full normalized/weighted breakdown for one scoring call."""
        raw: dict[Objective, float] = {
            "conversion_rate": cr,
            "revenue_per_user": rpu,
            "user_satisfaction": us,
        }
        now = datetime.now(UTC)

        if not self.enabled:
            score = ObjectiveScore(
                raw=raw,
                normalized={"conversion_rate": cr},
                weights_used={},
                normalization=self.normalization,
                total=cr,
                timestamp=now,
                enabled=False,
            )
            self._record_history(raw)
            return score

        active_weights = _normalize_weights(weights) if weights else self.get_weights()
        normalized = {
            objective: self._normalize_value(objective, raw[objective]) for objective in OBJECTIVES
        }
        total = sum(active_weights[o] * normalized[o] for o in OBJECTIVES)

        score = ObjectiveScore(
            raw=raw,
            normalized=normalized,
            weights_used=active_weights,
            normalization=self.normalization,
            total=total,
            timestamp=now,
            enabled=True,
        )
        self._record_history(raw)
        OBJECTIVE_SCORE.observe(total)
        self._logger.info(json.dumps({"event": "score", **score.as_dict()}))
        return score

    def _record_history(self, raw: dict[Objective, float]) -> None:
        with self._lock:
            self._history.append(dict(raw))

    def calculate_score(
        self,
        cr: float,
        rpu: float,
        us: float,
        weights: dict[Objective, float] | None = None,
    ) -> float:
        """Composite score for a routing decision (called during routing).

        Returns the raw `conversion_rate` when `FEATURE_MULTI_OBJECTIVE` is
        disabled, so callers can invoke this unconditionally.
        """
        return self.get_score_breakdown(cr, rpu, us, weights=weights).total

    def get_tradeoff_analysis(
        self,
        objective_a: Objective = "conversion_rate",
        objective_b: Objective = "revenue_per_user",
        *,
        min_samples: int = 5,
    ) -> TradeoffAnalysis:
        """Estimate how `objective_b` moves when `objective_a` moves, from history.

        `elasticity_pct` is the approximate percentage change in `objective_b`
        for a 1% increase in `objective_a`, derived from a linear fit over
        recorded (raw) scoring history.
        """
        with self._lock:
            samples = list(self._history)

        xs = [s[objective_a] for s in samples]
        ys = [s[objective_b] for s in samples]
        n = len(samples)

        if n < min_samples:
            return TradeoffAnalysis(
                objective_a=objective_a,
                objective_b=objective_b,
                sample_size=n,
                correlation=None,
                elasticity_pct=None,
                interpretation=(
                    f"Insufficient history ({n}/{min_samples} samples) for trade-off analysis."
                ),
            )

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / n
        var_x = sum((x - mean_x) ** 2 for x in xs) / n
        var_y = sum((y - mean_y) ** 2 for y in ys) / n

        correlation = cov / math.sqrt(var_x * var_y) if var_x > 0 and var_y > 0 else None
        elasticity_pct: float | None = None
        if var_x > 0 and mean_x != 0 and mean_y != 0:
            slope = cov / var_x
            elasticity_pct = slope * (mean_x / mean_y) * 1.0  # % change in y per 1% change in x

        if elasticity_pct is None:
            interpretation = "Not enough variance to estimate a trade-off."
        else:
            direction = "increases" if elasticity_pct >= 0 else "decreases"
            interpretation = (
                f"If {objective_a} increases by 1%, {objective_b} {direction} by "
                f"~{abs(elasticity_pct):.2f}% (n={n} samples)."
            )

        return TradeoffAnalysis(
            objective_a=objective_a,
            objective_b=objective_b,
            sample_size=n,
            correlation=correlation,
            elasticity_pct=elasticity_pct,
            interpretation=interpretation,
        )


# ---------------------------------------------------------------------------
# Admin API: POST /admin/objective/update_weights
#
# Standalone router kept decoupled from apps/api/app's auth stack (this
# module lives outside that package); it reuses the same ADMIN_API_TOKEN
# convention as apps/api/app/core/settings.py. Mount it with:
#     app.include_router(multi_objective.router)
# ---------------------------------------------------------------------------

_default_optimizer = ObjectiveOptimizer()


def get_optimizer() -> ObjectiveOptimizer:
    """Process-wide optimizer instance used by the admin router."""
    return _default_optimizer


async def _require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = os.getenv("ADMIN_API_TOKEN", "dev-admin-token")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


class UpdateWeightsPayload(BaseModel):
    conversion_rate: float = PydanticField(ge=0)
    revenue_per_user: float = PydanticField(ge=0)
    user_satisfaction: float = PydanticField(ge=0)


router = APIRouter(
    prefix="/admin/objective",
    tags=["admin-objective"],
    dependencies=[Depends(_require_admin_token)],
)


@router.post("/update_weights")
def update_weights_endpoint(
    payload: UpdateWeightsPayload,
    optimizer: ObjectiveOptimizer = Depends(get_optimizer),
) -> dict[str, Any]:
    weights = optimizer.update_weights(payload.model_dump())
    return {"weights": weights}
