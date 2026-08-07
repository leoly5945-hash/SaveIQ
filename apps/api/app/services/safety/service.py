"""Gate 10E safety orchestrator: kill switch + guardrailed auto-tune."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.settings import Settings
from app.services.safety.metrics_window import MetricsWindow, WindowSnapshot

logger = logging.getLogger(__name__)

CONFIG_KEY = "safety:config:v1"
HPARAMS_KEY = "safety:hparams:v1"
AUDIT_KEY = "safety:audit:v1"
AUDIT_MAX = 100

# Human-only — never auto-flipped by this service.
HUMAN_ONLY_FLAGS = (
    "feature_neural_bandit",
    "feature_rlhf_router",
    "feature_chinese_llm_providers",
    "bandit_policy",
)


@dataclass
class SafetyRuntimeConfig:
    """Runtime overlay on top of env feature flags."""

    kill_switch_enabled: bool = False
    auto_tune_enabled: bool = False
    manual_override: bool = False
    dry_run: bool = True
    auto_tune_canary_enabled: bool = False
    tripped: bool = False
    trip_reason: str | None = None
    trip_at: float | None = None
    last_evaluate_at: float | None = None
    last_tune_at: float | None = None
    actions_on_trip: list[str] = field(
        default_factory=lambda: ["stop_abtest", "zero_canary", "disable_autotune", "reset_hparams"]
    )


@dataclass
class TunableHParams:
    epsilon: float
    alpha: float
    beta: float
    gamma: float
    cache_ttl_seconds: int

    def clamped(self, settings: Settings) -> TunableHParams:
        eps_min = float(settings.auto_tune_epsilon_min)
        eps_max = float(settings.auto_tune_epsilon_max)
        ttl_min = int(settings.auto_tune_cache_ttl_min)
        ttl_max = int(settings.auto_tune_cache_ttl_max)
        alpha = max(0.0, min(1.0, float(self.alpha)))
        beta = max(0.0, min(1.0, float(self.beta)))
        gamma = max(0.0, min(1.0, float(self.gamma)))
        # Keep reward weights roughly summing near 1 when possible.
        total = alpha + beta + gamma
        if total > 0:
            alpha, beta, gamma = alpha / total, beta / total, gamma / total
        return TunableHParams(
            epsilon=max(eps_min, min(eps_max, float(self.epsilon))),
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            cache_ttl_seconds=max(ttl_min, min(ttl_max, int(self.cache_ttl_seconds))),
        )


class SafetyService:
    def __init__(self, settings: Settings, redis_client: Any | None = None) -> None:
        self._settings = settings
        self._redis = redis_client
        self._lock = threading.Lock()
        self._memory_config: SafetyRuntimeConfig | None = None
        self._memory_hparams: TunableHParams | None = None
        self._memory_audit: list[dict[str, Any]] = []
        self._window = MetricsWindow(window_seconds=settings.kill_switch_window_seconds)
        self._evaluate_lock = threading.Lock()

    def bootstrap_config(self) -> SafetyRuntimeConfig:
        return SafetyRuntimeConfig(
            kill_switch_enabled=bool(self._settings.feature_kill_switch),
            auto_tune_enabled=bool(self._settings.feature_auto_tuning),
            dry_run=bool(self._settings.auto_tune_dry_run),
            auto_tune_canary_enabled=bool(self._settings.auto_tune_canary_enabled),
        )

    def bootstrap_hparams(self) -> TunableHParams:
        return TunableHParams(
            epsilon=float(self._settings.bandit_epsilon),
            alpha=float(self._settings.bandit_reward_alpha),
            beta=float(self._settings.bandit_reward_beta),
            gamma=float(self._settings.bandit_reward_gamma),
            cache_ttl_seconds=int(self._settings.ai_router_cache_ttl_seconds),
        ).clamped(self._settings)

    def get_config(self) -> SafetyRuntimeConfig:
        if self._redis is not None:
            try:
                raw = self._redis.get(CONFIG_KEY)
                if raw:
                    data = json.loads(raw)
                    base = self.bootstrap_config()
                    return SafetyRuntimeConfig(
                        kill_switch_enabled=bool(
                            data.get("kill_switch_enabled", base.kill_switch_enabled)
                        ),
                        auto_tune_enabled=bool(
                            data.get("auto_tune_enabled", base.auto_tune_enabled)
                        ),
                        manual_override=bool(data.get("manual_override", False)),
                        dry_run=bool(data.get("dry_run", base.dry_run)),
                        auto_tune_canary_enabled=bool(
                            data.get("auto_tune_canary_enabled", base.auto_tune_canary_enabled)
                        ),
                        tripped=bool(data.get("tripped", False)),
                        trip_reason=data.get("trip_reason"),
                        trip_at=data.get("trip_at"),
                        last_evaluate_at=data.get("last_evaluate_at"),
                        last_tune_at=data.get("last_tune_at"),
                        actions_on_trip=list(data.get("actions_on_trip") or base.actions_on_trip),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Safety config read failed (%s)", exc.__class__.__name__)
        with self._lock:
            if self._memory_config is not None:
                return self._memory_config
        return self.bootstrap_config()

    def set_config(self, **updates: Any) -> SafetyRuntimeConfig:
        current = self.get_config()
        allowed = {
            "kill_switch_enabled",
            "auto_tune_enabled",
            "manual_override",
            "dry_run",
            "auto_tune_canary_enabled",
            "actions_on_trip",
        }
        payload = asdict(current)
        for key, value in updates.items():
            if key not in allowed or value is None:
                continue
            payload[key] = value
        updated = SafetyRuntimeConfig(
            kill_switch_enabled=bool(payload["kill_switch_enabled"]),
            auto_tune_enabled=bool(payload["auto_tune_enabled"]),
            manual_override=bool(payload["manual_override"]),
            dry_run=bool(payload["dry_run"]),
            auto_tune_canary_enabled=bool(payload["auto_tune_canary_enabled"]),
            tripped=bool(payload.get("tripped", False)),
            trip_reason=payload.get("trip_reason"),
            trip_at=payload.get("trip_at"),
            last_evaluate_at=payload.get("last_evaluate_at"),
            last_tune_at=payload.get("last_tune_at"),
            actions_on_trip=list(payload.get("actions_on_trip") or current.actions_on_trip),
        )
        self._persist_config(updated)
        self._audit(
            "config_update",
            {
                "updates": {
                    k: updates[k] for k in updates if k in allowed and updates[k] is not None
                }
            },
        )
        return updated

    def get_hparams(self) -> TunableHParams:
        if self._redis is not None:
            try:
                raw = self._redis.get(HPARAMS_KEY)
                if raw:
                    data = json.loads(raw)
                    return TunableHParams(
                        epsilon=float(data["epsilon"]),
                        alpha=float(data["alpha"]),
                        beta=float(data["beta"]),
                        gamma=float(data["gamma"]),
                        cache_ttl_seconds=int(data["cache_ttl_seconds"]),
                    ).clamped(self._settings)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Safety hparams read failed (%s)", exc.__class__.__name__)
        with self._lock:
            if self._memory_hparams is not None:
                return self._memory_hparams.clamped(self._settings)
        return self.bootstrap_hparams()

    def set_hparams(self, hparams: TunableHParams, *, reason: str) -> TunableHParams:
        clamped = hparams.clamped(self._settings)
        previous = self.get_hparams()
        self._persist_hparams(clamped)
        self._apply_hparams_to_runtime(clamped)
        self._audit(
            "hparams_update",
            {
                "reason": reason,
                "previous": asdict(previous),
                "next": asdict(clamped),
            },
        )
        return clamped

    def reset_hparams(self, *, reason: str = "reset_to_env_defaults") -> TunableHParams:
        defaults = self.bootstrap_hparams()
        return self.set_hparams(defaults, reason=reason)

    def record_request(
        self,
        *,
        status_code: int,
        latency_ms: float,
        cost_usd: float = 0.0,
        success: bool | None = None,
    ) -> None:
        config = self.get_config()
        if not (config.kill_switch_enabled or config.auto_tune_enabled):
            return
        self._window.configure(window_seconds=self._settings.kill_switch_window_seconds)
        self._window.record(
            status_code=status_code,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=success,
        )

    def window_snapshot(self) -> WindowSnapshot:
        self._window.configure(window_seconds=self._settings.kill_switch_window_seconds)
        return self._window.snapshot()

    def status(self) -> dict[str, Any]:
        config = self.get_config()
        hparams = self.get_hparams()
        snap = self.window_snapshot()
        return {
            "env": {
                "feature_kill_switch": self._settings.feature_kill_switch,
                "feature_auto_tuning": self._settings.feature_auto_tuning,
                "auto_tune_dry_run": self._settings.auto_tune_dry_run,
                "auto_tune_canary_enabled": self._settings.auto_tune_canary_enabled,
            },
            "runtime": asdict(config),
            "hparams": asdict(hparams),
            "thresholds": {
                "window_seconds": self._settings.kill_switch_window_seconds,
                "min_samples": self._settings.kill_switch_min_samples,
                "error_rate": self._settings.kill_switch_error_rate_threshold,
                "latency_p95_ms": self._settings.kill_switch_latency_p95_ms,
                "cost_usd_per_min": self._settings.kill_switch_cost_usd_per_min,
                "auto_tune_min_samples": self._settings.auto_tune_min_samples,
                "auto_tune_interval_seconds": self._settings.auto_tune_interval_seconds,
                "canary_max_pct": self._settings.auto_tune_canary_max_pct,
                "canary_step_pct": self._settings.auto_tune_canary_step_pct,
                "epsilon_min": self._settings.auto_tune_epsilon_min,
                "epsilon_max": self._settings.auto_tune_epsilon_max,
                "cache_ttl_min": self._settings.auto_tune_cache_ttl_min,
                "cache_ttl_max": self._settings.auto_tune_cache_ttl_max,
            },
            "window": asdict(snap),
            "human_only_flags": list(HUMAN_ONLY_FLAGS),
            "effective": {
                "kill_armed": bool(config.kill_switch_enabled) and not config.manual_override,
                "auto_tune_armed": (
                    bool(config.auto_tune_enabled)
                    and not config.manual_override
                    and not config.tripped
                ),
            },
        }

    def audit_log(self, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(AUDIT_MAX, int(limit)))
        if self._redis is not None:
            try:
                raw = self._redis.lrange(AUDIT_KEY, 0, limit - 1)
                out: list[dict[str, Any]] = []
                for item in raw or []:
                    out.append(json.loads(item))
                return out
            except Exception as exc:  # noqa: BLE001
                logger.warning("Safety audit read failed (%s)", exc.__class__.__name__)
        with self._lock:
            return list(self._memory_audit[:limit])

    def trip(self, reason: str, *, force: bool = False) -> dict[str, Any]:
        config = self.get_config()
        if config.manual_override and not force:
            return {
                "tripped": False,
                "skipped": True,
                "reason": "manual_override",
                "message": "Kill switch suppressed by manual_override (use force=true to override)",
            }
        if not config.kill_switch_enabled and not force:
            return {
                "tripped": False,
                "skipped": True,
                "reason": "kill_switch_disabled",
            }

        actions_taken: list[dict[str, Any]] = []
        config.tripped = True
        config.trip_reason = reason
        config.trip_at = time.time()

        for action in config.actions_on_trip:
            result = self._run_trip_action(action)
            actions_taken.append({"action": action, **result})

        self._persist_config(config)
        self._audit("kill_trip", {"reason": reason, "actions": actions_taken, "force": force})
        try:
            from app.observability.metrics import observe_kill_switch_trip

            observe_kill_switch_trip(reason=reason)
        except Exception:  # noqa: BLE001
            pass
        return {
            "tripped": True,
            "reason": reason,
            "actions": actions_taken,
            "runtime": asdict(config),
        }

    def disarm(self, *, clear_window: bool = False) -> dict[str, Any]:
        config = self.get_config()
        config.tripped = False
        config.trip_reason = None
        config.trip_at = None
        self._persist_config(config)
        if clear_window:
            self._window.clear()
        self._audit("kill_disarm", {"clear_window": clear_window})
        return {"tripped": False, "runtime": asdict(config)}

    def evaluate(self, *, force_tune: bool = False) -> dict[str, Any]:
        """Run kill-switch checks then (if safe) auto-tune proposals/applies."""
        if not self._evaluate_lock.acquire(blocking=False):
            return {"skipped": True, "reason": "evaluate_in_progress"}
        try:
            config = self.get_config()
            snap = self.window_snapshot()
            result: dict[str, Any] = {
                "window": asdict(snap),
                "kill": None,
                "tune": None,
                "manual_override": config.manual_override,
            }

            config.last_evaluate_at = time.time()
            self._persist_config(config)

            if config.manual_override:
                result["kill"] = {"skipped": True, "reason": "manual_override"}
                result["tune"] = {"skipped": True, "reason": "manual_override"}
                return result

            if config.kill_switch_enabled:
                breach = self._check_breaches(snap)
                if breach and not config.tripped:
                    result["kill"] = self.trip(breach)
                elif config.tripped:
                    result["kill"] = {
                        "already_tripped": True,
                        "reason": config.trip_reason,
                    }
                else:
                    result["kill"] = {"ok": True, "breach": None}
            else:
                result["kill"] = {"skipped": True, "reason": "kill_switch_disabled"}

            config = self.get_config()
            if config.tripped:
                result["tune"] = {"skipped": True, "reason": "kill_tripped"}
                return result

            if not config.auto_tune_enabled:
                result["tune"] = {"skipped": True, "reason": "auto_tune_disabled"}
                return result

            result["tune"] = self._auto_tune(snap, force=force_tune)
            return result
        finally:
            self._evaluate_lock.release()

    def maybe_background_tick(self) -> None:
        """Cheap periodic evaluate from request path (rate-limited)."""
        config = self.get_config()
        if not (config.kill_switch_enabled or config.auto_tune_enabled):
            return
        if config.manual_override:
            return
        last = config.last_evaluate_at or 0.0
        interval = max(15, int(self._settings.auto_tune_interval_seconds) // 4)
        if time.time() - last < interval:
            return
        try:
            self.evaluate()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Safety background evaluate failed (%s)", exc.__class__.__name__)

    def _check_breaches(self, snap: WindowSnapshot) -> str | None:
        min_samples = int(self._settings.kill_switch_min_samples)
        if snap.requests < min_samples:
            return None
        if snap.error_rate >= float(self._settings.kill_switch_error_rate_threshold):
            return (
                f"error_rate={snap.error_rate:.4f} "
                f">= {self._settings.kill_switch_error_rate_threshold}"
            )
        if snap.latency_p95_ms >= float(self._settings.kill_switch_latency_p95_ms):
            return (
                f"latency_p95_ms={snap.latency_p95_ms:.1f} "
                f">= {self._settings.kill_switch_latency_p95_ms}"
            )
        if snap.cost_usd_per_min >= float(self._settings.kill_switch_cost_usd_per_min):
            return (
                f"cost_usd_per_min={snap.cost_usd_per_min:.4f} "
                f">= {self._settings.kill_switch_cost_usd_per_min}"
            )
        return None

    def _auto_tune(self, snap: WindowSnapshot, *, force: bool) -> dict[str, Any]:
        config = self.get_config()
        min_samples = int(self._settings.auto_tune_min_samples)
        if snap.requests < min_samples and not force:
            return {
                "skipped": True,
                "reason": "insufficient_samples",
                "have": snap.requests,
                "need": min_samples,
            }

        interval = int(self._settings.auto_tune_interval_seconds)
        last = config.last_tune_at or 0.0
        if not force and time.time() - last < interval:
            return {
                "skipped": True,
                "reason": "interval_not_elapsed",
                "seconds_remaining": max(0, int(interval - (time.time() - last))),
            }

        current = self.get_hparams()
        proposed = TunableHParams(
            epsilon=current.epsilon,
            alpha=current.alpha,
            beta=current.beta,
            gamma=current.gamma,
            cache_ttl_seconds=current.cache_ttl_seconds,
        )
        reasons: list[str] = []

        # Latency pressure → stronger latency weight + longer cache TTL.
        latency_budget = float(self._settings.kill_switch_latency_p95_ms)
        if snap.latency_p95_ms > 0.7 * latency_budget:
            proposed.gamma = min(1.0, proposed.gamma + 0.05)
            proposed.cache_ttl_seconds = min(
                int(self._settings.auto_tune_cache_ttl_max),
                proposed.cache_ttl_seconds + 60,
            )
            reasons.append("latency_pressure")
        elif snap.latency_p95_ms < 0.3 * latency_budget and snap.success_rate >= 0.9:
            proposed.cache_ttl_seconds = max(
                int(self._settings.auto_tune_cache_ttl_min),
                proposed.cache_ttl_seconds - 30,
            )
            reasons.append("latency_headroom")

        # Cost pressure → higher cost weight, less exploration.
        cost_budget = float(self._settings.kill_switch_cost_usd_per_min)
        if snap.cost_usd_per_min > 0.5 * cost_budget:
            proposed.beta = min(1.0, proposed.beta + 0.05)
            proposed.epsilon = max(
                float(self._settings.auto_tune_epsilon_min),
                proposed.epsilon - 0.02,
            )
            reasons.append("cost_pressure")

        # Low success / CTR proxy → mild exploration bump (within caps).
        if snap.success_rate < 0.7 and snap.latency_p95_ms < 0.8 * latency_budget:
            proposed.epsilon = min(
                float(self._settings.auto_tune_epsilon_max),
                proposed.epsilon + 0.02,
            )
            proposed.alpha = min(1.0, proposed.alpha + 0.03)
            reasons.append("low_success_explore")

        proposed = proposed.clamped(self._settings)
        canary_action: dict[str, Any] | None = None
        if config.auto_tune_canary_enabled:
            canary_action = self._propose_canary_step(snap)

        changed = asdict(proposed) != asdict(current)
        if not reasons and not canary_action:
            config.last_tune_at = time.time()
            self._persist_config(config)
            return {"applied": False, "reason": "no_adjustment_needed", "hparams": asdict(current)}

        proposal = {
            "previous": asdict(current),
            "proposed": asdict(proposed),
            "reasons": reasons,
            "canary": canary_action,
            "dry_run": config.dry_run,
            "metric_window": asdict(snap),
        }

        if config.dry_run:
            self._audit("autotune_propose", proposal)
            config.last_tune_at = time.time()
            self._persist_config(config)
            try:
                from app.observability.metrics import observe_auto_tune_action

                observe_auto_tune_action(result="propose")
            except Exception:  # noqa: BLE001
                pass
            return {"applied": False, "dry_run": True, **proposal}

        if changed:
            self.set_hparams(proposed, reason=";".join(reasons) or "autotune")
        if canary_action and canary_action.get("apply"):
            self._apply_canary_percentage(int(canary_action["next_percentage"]))
            self._audit("autotune_canary", canary_action)

        config = self.get_config()
        config.last_tune_at = time.time()
        self._persist_config(config)
        try:
            from app.observability.metrics import observe_auto_tune_action

            observe_auto_tune_action(result="apply")
        except Exception:  # noqa: BLE001
            pass
        return {"applied": True, "dry_run": False, **proposal}

    def _propose_canary_step(self, snap: WindowSnapshot) -> dict[str, Any] | None:
        """Adjust canary within 0..max step caps; skip when A/B is running."""
        from app.services.abtest.service import build_abtest_service
        from app.services.canary.service import build_canary_service

        ab = build_abtest_service(self._settings)
        ab_status = ab.status()
        if ab_status.get("running"):
            return {
                "skipped": True,
                "reason": "abtest_running",
                "note": "Auto-tune will not change canary while A/B is active",
            }

        canary = build_canary_service(self._settings)
        cfg = canary.get_config()
        current_pct = int(cfg.percentage) if cfg.enabled else 0
        max_pct = max(0, min(25, int(self._settings.auto_tune_canary_max_pct)))
        step = max(1, min(5, int(self._settings.auto_tune_canary_step_pct)))
        error_budget = float(self._settings.kill_switch_error_rate_threshold)

        next_pct = current_pct
        reason = "hold"
        if snap.error_rate > 0.5 * error_budget and current_pct > 0:
            next_pct = max(0, current_pct - step)
            reason = "error_pressure_down"
        elif (
            snap.error_rate < 0.25 * error_budget
            and snap.latency_p95_ms < 0.5 * float(self._settings.kill_switch_latency_p95_ms)
            and current_pct < max_pct
        ):
            next_pct = min(max_pct, current_pct + step)
            reason = "healthy_up"

        if next_pct == current_pct:
            return {"skipped": True, "reason": "no_canary_change", "percentage": current_pct}

        return {
            "apply": True,
            "reason": reason,
            "previous_percentage": current_pct,
            "next_percentage": next_pct,
            "enabled": next_pct > 0,
        }

    def _apply_canary_percentage(self, percentage: int) -> None:
        from app.services.canary.service import build_canary_service

        service = build_canary_service(self._settings)
        pct = max(0, min(int(self._settings.auto_tune_canary_max_pct), int(percentage)))
        service.set_config(enabled=pct > 0, percentage=pct)

    def _run_trip_action(self, action: str) -> dict[str, Any]:
        try:
            if action == "stop_abtest":
                from app.services.abtest.service import build_abtest_service

                status = build_abtest_service(self._settings).stop()
                return {"ok": True, "abtest": status}
            if action == "zero_canary":
                from app.services.canary.service import build_canary_service

                cfg = build_canary_service(self._settings).set_config(enabled=False, percentage=0)
                return {
                    "ok": True,
                    "canary": {"enabled": cfg.enabled, "percentage": cfg.percentage},
                }
            if action == "disable_autotune":
                config = self.get_config()
                config.auto_tune_enabled = False
                self._persist_config(config)
                return {"ok": True, "auto_tune_enabled": False}
            if action == "reset_hparams":
                hparams = self.reset_hparams(reason="kill_switch_reset")
                return {"ok": True, "hparams": asdict(hparams)}
            return {"ok": False, "error": f"unknown_action:{action}"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Kill switch action %s failed", action)
            return {"ok": False, "error": exc.__class__.__name__}

    def _apply_hparams_to_runtime(self, hparams: TunableHParams) -> None:
        try:
            from app.services.bandit.service import build_bandit_router_service

            bandit = build_bandit_router_service(self._settings)
            bandit.apply_runtime_hparams(
                epsilon=hparams.epsilon,
                alpha=hparams.alpha,
                beta=hparams.beta,
                gamma=hparams.gamma,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bandit hparam apply failed (%s)", exc.__class__.__name__)
        try:
            from app.services.router.ai_router import apply_runtime_cache_ttl

            apply_runtime_cache_ttl(hparams.cache_ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache TTL apply failed (%s)", exc.__class__.__name__)

    def _persist_config(self, config: SafetyRuntimeConfig) -> None:
        payload = asdict(config)
        if self._redis is not None:
            try:
                self._redis.set(CONFIG_KEY, json.dumps(payload))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Safety config write failed (%s)", exc.__class__.__name__)
        with self._lock:
            self._memory_config = config

    def _persist_hparams(self, hparams: TunableHParams) -> None:
        payload = asdict(hparams)
        if self._redis is not None:
            try:
                self._redis.set(HPARAMS_KEY, json.dumps(payload))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Safety hparams write failed (%s)", exc.__class__.__name__)
        with self._lock:
            self._memory_hparams = hparams

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        entry = {"ts": time.time(), "event": event, **payload}
        if self._redis is not None:
            try:
                self._redis.lpush(AUDIT_KEY, json.dumps(entry, default=str))
                self._redis.ltrim(AUDIT_KEY, 0, AUDIT_MAX - 1)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Safety audit write failed (%s)", exc.__class__.__name__)
        with self._lock:
            self._memory_audit.insert(0, entry)
            del self._memory_audit[AUDIT_MAX:]


_service: SafetyService | None = None
_service_lock = threading.Lock()


def build_safety_service(settings: Settings) -> SafetyService:
    global _service
    with _service_lock:
        if _service is None:
            from app.services.router.redis_client import create_redis_client

            client = create_redis_client(settings.redis_url)
            _service = SafetyService(settings, client)
        else:
            _service._settings = settings  # noqa: SLF001
        return _service


def reset_safety_service_for_tests() -> None:
    global _service
    with _service_lock:
        if _service is not None:
            if _service._redis is not None:  # noqa: SLF001
                try:
                    _service._redis.delete(CONFIG_KEY, HPARAMS_KEY, AUDIT_KEY)  # noqa: SLF001
                except Exception:  # noqa: BLE001
                    pass
            _service._window.clear()  # noqa: SLF001
            _service._memory_config = None  # noqa: SLF001
            _service._memory_hparams = None  # noqa: SLF001
            _service._memory_audit.clear()  # noqa: SLF001
        _service = None
