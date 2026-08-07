"""Sticky A/B assignment, exposure logging, and significance (Gate 10D)."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped,unused-ignore]

from app.core.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_EXPERIMENT = "router_holdout_v1"
STATS_KEY_TMPL = "abtest:stats:{experiment}"
ASSIGN_KEY_TMPL = "abtest:{experiment}:{user_id}"


def _resolve_config_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    here = Path(__file__).resolve()
    search = [
        Path.cwd() / path,
        here.parents[3] / path,  # apps/api/config/...
        here.parents[5] / path,  # repo root config/...
    ]
    for item in search:
        if item.is_file():
            return item
    return candidate


class ABTestService:
    def __init__(
        self,
        settings: Settings,
        redis_client: Any | None = None,
        *,
        config_path: str | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client
        self._lock = threading.Lock()
        self._config_path = config_path or settings.abtest_config_path
        self._ttl = int(settings.abtest_redis_ttl)
        self._file_config: dict[str, Any] = {}
        self._runtime: dict[str, Any] = {
            "feature_enabled": bool(settings.feature_abtest_enabled),
            "running": False,
            "active_experiment": None,
        }
        self._memory_assign: dict[str, str] = {}
        self._memory_stats: dict[str, dict[str, int]] = {}
        self.reload_config()

    @property
    def feature_enabled(self) -> bool:
        return bool(self._runtime.get("feature_enabled"))

    def set_feature_enabled(self, enabled: bool) -> None:
        self._runtime["feature_enabled"] = enabled

    def reload_config(self) -> dict[str, Any]:
        path = _resolve_config_path(self._config_path)
        if not path.is_file():
            logger.warning("A/B config missing at %s; using empty defaults", path)
            self._file_config = {
                "active_experiment": DEFAULT_EXPERIMENT,
                "experiments": {},
            }
            return self._file_config
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("abtest.yaml must be a mapping")
        self._file_config = data
        if self._runtime.get("active_experiment") is None:
            self._runtime["active_experiment"] = data.get("active_experiment")
        return self._file_config

    def list_experiments(self) -> dict[str, Any]:
        return dict(self._file_config.get("experiments") or {})

    def active_experiment_name(self) -> str | None:
        return self._runtime.get("active_experiment") or self._file_config.get("active_experiment")

    def get_experiment(self, experiment_name: str | None = None) -> dict[str, Any]:
        name = experiment_name or self.active_experiment_name() or DEFAULT_EXPERIMENT
        experiments = self.list_experiments()
        exp = experiments.get(name)
        if not isinstance(exp, dict):
            return {"name": name, "enabled": False, "groups": {}}
        return {"name": name, **exp}

    def status(self) -> dict[str, Any]:
        name = self.active_experiment_name()
        exp = self.get_experiment(name)
        return {
            "feature_enabled": self.feature_enabled,
            "running": bool(self._runtime.get("running")) and self.feature_enabled,
            "active_experiment": name,
            "config_path": str(_resolve_config_path(self._config_path)),
            "redis_ttl_seconds": self._ttl,
            "experiment": {
                "name": exp.get("name"),
                "enabled": bool(exp.get("enabled")),
                "description": exp.get("description"),
                "groups": list((exp.get("groups") or {}).keys()),
                "traffic_percent": exp.get("traffic_percent", 100),
            },
        }

    def start(self, experiment_name: str | None = None) -> dict[str, Any]:
        if experiment_name:
            if experiment_name not in self.list_experiments():
                raise ValueError(f"Unknown experiment: {experiment_name}")
            self._runtime["active_experiment"] = experiment_name
        self._runtime["feature_enabled"] = True
        self._runtime["running"] = True
        # Mark experiment enabled in runtime overlay (does not rewrite YAML).
        name = self.active_experiment_name()
        experiments = self._file_config.setdefault("experiments", {})
        if name and name in experiments and isinstance(experiments[name], dict):
            experiments[name]["enabled"] = True
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._runtime["running"] = False
        name = self.active_experiment_name()
        experiments = self._file_config.get("experiments") or {}
        if name and isinstance(experiments.get(name), dict):
            experiments[name]["enabled"] = False
        return self.status()

    def update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "feature_enabled" in payload:
            self._runtime["feature_enabled"] = bool(payload["feature_enabled"])
        if "running" in payload:
            self._runtime["running"] = bool(payload["running"])
        if "active_experiment" in payload and payload["active_experiment"]:
            name = str(payload["active_experiment"])
            if name not in self.list_experiments():
                raise ValueError(f"Unknown experiment: {name}")
            self._runtime["active_experiment"] = name
        if "experiment" in payload and isinstance(payload["experiment"], dict):
            name = self.active_experiment_name() or DEFAULT_EXPERIMENT
            experiments = self._file_config.setdefault("experiments", {})
            current = dict(experiments.get(name) or {})
            current.update(payload["experiment"])
            experiments[name] = current
        if "reload" in payload and payload["reload"]:
            self.reload_config()
        return self.status()

    def assign_user(self, user_id: str, experiment_name: str | None = None) -> str:
        if not user_id:
            return "none"
        if not self.feature_enabled or not self._runtime.get("running"):
            return "none"
        exp_name = experiment_name or self.active_experiment_name() or DEFAULT_EXPERIMENT
        exp = self.get_experiment(exp_name)
        groups = exp.get("groups") or {}
        if not groups:
            return "none"

        cached = self._get_assignment(exp_name, user_id)
        if cached is not None:
            return cached

        traffic = max(0, min(100, int(exp.get("traffic_percent", 100))))
        bucket = self._bucket(user_id, exp_name)
        if bucket >= traffic:
            group = "none"
        else:
            group = self._pick_group(user_id, exp_name, groups)
        self._set_assignment(exp_name, user_id, group)
        return group

    def get_config(self, user_id: str, experiment_name: str | None = None) -> dict[str, Any]:
        exp_name = experiment_name or self.active_experiment_name() or DEFAULT_EXPERIMENT
        group = self.assign_user(user_id, exp_name)
        exp = self.get_experiment(exp_name)
        groups = exp.get("groups") or {}
        group_cfg = groups.get(group) if isinstance(groups.get(group), dict) else {}
        overrides = dict(group_cfg.get("config") or {}) if isinstance(group_cfg, dict) else {}
        return {
            "experiment": exp_name,
            "group": group,
            "config": overrides,
        }

    def log_exposure(
        self,
        user_id: str,
        group: str,
        experiment: str | None = None,
        *,
        converted: bool = False,
    ) -> None:
        exp_name = experiment or self.active_experiment_name() or DEFAULT_EXPERIMENT
        if group in {"", "none", None}:
            return
        self._bump_stat(exp_name, f"{group}:exposures", 1)
        if converted:
            self._bump_stat(exp_name, f"{group}:conversions", 1)

    def get_stats(self, experiment_name: str | None = None) -> dict[str, Any]:
        exp_name = experiment_name or self.active_experiment_name() or DEFAULT_EXPERIMENT
        raw = self._read_stats(exp_name)
        exp = self.get_experiment(exp_name)
        groups = list((exp.get("groups") or {}).keys())
        by_group: dict[str, dict[str, int | float]] = {}
        for group in groups:
            exposures = int(raw.get(f"{group}:exposures", 0))
            conversions = int(raw.get(f"{group}:conversions", 0))
            by_group[group] = {
                "exposures": exposures,
                "conversions": conversions,
                "conversion_rate": (round(conversions / exposures, 6) if exposures > 0 else 0.0),
            }
        return {
            "experiment": exp_name,
            "groups": by_group,
            "raw": raw,
        }

    def calculate_significance(
        self,
        experiment_name: str | None = None,
        metric: str = "conversions",
    ) -> dict[str, Any]:
        """Chi-square test on control vs first treatment for binary metric counts."""
        from scipy.stats import chi2_contingency  # type: ignore[import-untyped,unused-ignore]

        stats = self.get_stats(experiment_name)
        groups = stats["groups"]
        names = list(groups.keys())
        if len(names) < 2:
            return {
                "experiment": stats["experiment"],
                "metric": metric,
                "error": "need at least two groups",
                "significant": False,
            }
        control_name = "control" if "control" in groups else names[0]
        treatment_name = next(n for n in names if n != control_name)
        control = groups[control_name]
        treatment = groups[treatment_name]
        if metric != "conversions":
            # Extensible later; currently only conversion contingency is supported.
            return {
                "experiment": stats["experiment"],
                "metric": metric,
                "error": "unsupported metric; use conversions",
                "significant": False,
            }
        c_exp = int(control["exposures"])
        c_conv = int(control["conversions"])
        t_exp = int(treatment["exposures"])
        t_conv = int(treatment["conversions"])
        c_fail = max(c_exp - c_conv, 0)
        t_fail = max(t_exp - t_conv, 0)
        table = [[c_conv, c_fail], [t_conv, t_fail]]
        # Degenerate tables (e.g. all conversions=0 from exposure-only traffic)
        # make chi2 undefined — return a structured error instead of raising.
        if (
            c_exp == 0
            or t_exp == 0
            or sum(sum(row) for row in table) == 0
            or (c_conv + t_conv) == 0
            or (c_fail + t_fail) == 0
        ):
            return {
                "experiment": stats["experiment"],
                "metric": metric,
                "control": control_name,
                "treatment": treatment_name,
                "table": table,
                "error": "insufficient or degenerate conversion table",
                "significant": False,
                "p_value": None,
            }
        try:
            chi2, p_value, dof, expected = chi2_contingency(table)
        except ValueError as exc:
            return {
                "experiment": stats["experiment"],
                "metric": metric,
                "control": control_name,
                "treatment": treatment_name,
                "table": table,
                "error": f"chi2_unavailable: {exc}",
                "significant": False,
                "p_value": None,
            }
        alpha = 0.05
        return {
            "experiment": stats["experiment"],
            "metric": metric,
            "control": control_name,
            "treatment": treatment_name,
            "table": table,
            "chi2": float(chi2),
            "p_value": float(p_value),
            "dof": int(dof),
            "expected": expected.tolist() if hasattr(expected, "tolist") else expected,
            "alpha": alpha,
            "significant": bool(p_value < alpha),
        }

    def _bucket(self, user_id: str, experiment_name: str) -> int:
        digest = hashlib.md5(f"{experiment_name}:{user_id}".encode()).hexdigest()
        return int(digest[:8], 16) % 100

    def _pick_group(self, user_id: str, experiment_name: str, groups: dict[str, Any]) -> str:
        # Stable secondary hash for within-traffic split.
        digest = hashlib.md5(f"{experiment_name}:{user_id}:group".encode()).hexdigest()
        slot = int(digest[:8], 16) % 100
        cursor = 0
        ordered = sorted(groups.items(), key=lambda item: item[0])
        for name, spec in ordered:
            percent = int((spec or {}).get("percent", 0))
            cursor += max(0, percent)
            if slot < cursor:
                return name
        # Fallback to last group if percents don't sum to 100.
        return ordered[-1][0] if ordered else "none"

    def _assign_key(self, experiment: str, user_id: str) -> str:
        return ASSIGN_KEY_TMPL.format(experiment=experiment, user_id=user_id)

    def _get_assignment(self, experiment: str, user_id: str) -> str | None:
        key = self._assign_key(experiment, user_id)
        if self._redis is not None:
            try:
                value = self._redis.get(key)
                if value is not None:
                    return str(value)
            except Exception as exc:  # noqa: BLE001
                logger.warning("A/B assignment read failed (%s)", exc.__class__.__name__)
        with self._lock:
            return self._memory_assign.get(key)

    def _set_assignment(self, experiment: str, user_id: str, group: str) -> None:
        key = self._assign_key(experiment, user_id)
        if self._redis is not None:
            try:
                self._redis.setex(key, self._ttl, group)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("A/B assignment write failed (%s)", exc.__class__.__name__)
        with self._lock:
            self._memory_assign[key] = group

    def _bump_stat(self, experiment: str, field: str, amount: int = 1) -> None:
        key = STATS_KEY_TMPL.format(experiment=experiment)
        if self._redis is not None:
            try:
                self._redis.hincrby(key, field, amount)
                self._redis.expire(key, self._ttl)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("A/B stats write failed (%s)", exc.__class__.__name__)
        with self._lock:
            bucket = self._memory_stats.setdefault(experiment, {})
            bucket[field] = int(bucket.get(field, 0)) + amount

    def _read_stats(self, experiment: str) -> dict[str, int]:
        key = STATS_KEY_TMPL.format(experiment=experiment)
        if self._redis is not None:
            try:
                raw = self._redis.hgetall(key) or {}
                return {str(k): int(float(v)) for k, v in raw.items()}
            except Exception as exc:  # noqa: BLE001
                logger.warning("A/B stats read failed (%s)", exc.__class__.__name__)
        with self._lock:
            return dict(self._memory_stats.get(experiment, {}))


_service: ABTestService | None = None
_service_lock = threading.Lock()


def build_abtest_service(settings: Settings) -> ABTestService:
    global _service
    with _service_lock:
        if _service is None:
            from app.services.router.redis_client import create_redis_client

            client = create_redis_client(settings.redis_url)
            _service = ABTestService(settings, client)
        else:
            _service._settings = settings
        return _service


def reset_abtest_service_for_tests() -> None:
    global _service
    with _service_lock:
        if _service is not None and _service._redis is not None:
            try:
                # Best-effort cleanup of known keys is skipped; tests use memory clients.
                pass
            except Exception:  # noqa: BLE001
                pass
        _service = None


def dump_runtime_for_debug(service: ABTestService) -> str:
    return json.dumps(service.status())
