#!/usr/bin/env python3
"""Automate Gate 10E staging drill + production canary C3/C4 + mock router.

Safety principles
-----------------
- Never enables production FEATURE_KILL_SWITCH / FEATURE_AUTO_TUNING.
- Staging drill must pass before any production canary advance.
- Each canary advance requires a minimum soak (default 24h) recorded in a
  local state file before the next phase may run.
- On hard failure during a production canary mutate: rollback canary to the
  previous percentage (or zero if unknown).
- Secrets only from environment: STAGING_ADMIN_TOKEN, PROD_ADMIN_TOKEN
  (aliases: ADMIN_API_TOKEN_STAGING / ADMIN_API_TOKEN for prod).

Phases
------
  staging_drill  Kill-switch trip + auto-tune dry-run on staging only
  c3             Production canary → 25% (requires C2 + staging_drill pass)
  soak_c3        Verify ≥ soak elapsed since C3 (no mutation)
  c4             Production canary → 100% (requires soak_c3)
  soak_c4        Verify ≥ soak elapsed since C4
  mock_router    Ensure C4 + router feature (mock path via canary effective mode)
  status         Print state + live snapshots
  rollback       Immediate production canary disable (percentage=0)

Usage
-----
  export STAGING_ADMIN_TOKEN=...
  export PROD_ADMIN_TOKEN=...

  # Full pipeline (will STOP and wait if soak not elapsed)
  .venv/bin/python scripts/gate10e_rollout.py --phase all

  # One step at a time
  .venv/bin/python scripts/gate10e_rollout.py --phase staging_drill
  .venv/bin/python scripts/gate10e_rollout.py --phase c3
  .venv/bin/python scripts/gate10e_rollout.py --phase soak_c3
  .venv/bin/python scripts/gate10e_rollout.py --phase c4

  # Local testing only (DO NOT use in real prod rollouts)
  .venv/bin/python scripts/gate10e_rollout.py --phase all --soak-seconds 60

  # Emergency
  .venv/bin/python scripts/gate10e_rollout.py --phase rollback
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_STAGING_API = "https://dealhunter-staging-api.onrender.com"
DEFAULT_PROD_API = "https://dealhunter-production-api.onrender.com"
DEFAULT_PROD_WEB = "https://dealhunter-production-web.onrender.com"
USER_AGENT = "SaveIQ-Gate10E-Rollout/1.0"
DEFAULT_SOAK_SECONDS = 24 * 60 * 60
CANARY_FEATURES = ["router", "bandit", "personalization", "llm_cn"]
STATE_VERSION = 1

PHASES = (
    "staging_drill",
    "c3",
    "soak_c3",
    "c4",
    "soak_c4",
    "mock_router",
    "status",
    "rollback",
    "all",
)


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


@dataclass
class RolloutState:
    version: int = STATE_VERSION
    staging_drill_passed_at: float | None = None
    c3_set_at: float | None = None
    c3_percentage: int | None = None
    c4_set_at: float | None = None
    c4_percentage: int | None = None
    mock_router_ready_at: float | None = None
    last_rollback_at: float | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> RolloutState:
        if not path.is_file():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return cls()
        return cls(
            version=int(raw.get("version") or STATE_VERSION),
            staging_drill_passed_at=_opt_float(raw.get("staging_drill_passed_at")),
            c3_set_at=_opt_float(raw.get("c3_set_at")),
            c3_percentage=_opt_int(raw.get("c3_percentage")),
            c4_set_at=_opt_float(raw.get("c4_set_at")),
            c4_percentage=_opt_int(raw.get("c4_percentage")),
            mock_router_ready_at=_opt_float(raw.get("mock_router_ready_at")),
            last_rollback_at=_opt_float(raw.get("last_rollback_at")),
            history=list(raw.get("history") or []),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def note(self, event: str, **extra: Any) -> None:
        entry = {"ts": time.time(), "event": event, **extra}
        self.history.append(entry)
        self.history = self.history[-200:]


class RolloutError(RuntimeError):
    pass


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def log(msg: str) -> None:
    print(msg, flush=True)


def http_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: dict[str, Any] | None = None,
    expected: int | None = 200,
    timeout: float = 60.0,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Admin-Token"] = token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
        if expected is not None and status != expected:
            raise RolloutError(
                f"{method} {url} -> HTTP {status}: {payload[:500]}"
            ) from exc
        parsed = json.loads(payload) if payload else {}
        if isinstance(parsed, dict):
            parsed["_status"] = status
            return parsed
        return {"_status": status, "_raw": payload}
    except Exception as exc:  # noqa: BLE001
        raise RolloutError(f"{method} {url} failed: {exc}") from exc

    if expected is not None and status != expected:
        raise RolloutError(f"{method} {url} -> HTTP {status}: {payload[:500]}")
    if not payload:
        return {}
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise RolloutError(f"{url} did not return a JSON object")
    return parsed


def require_token(*, staging: bool) -> str:
    if staging:
        token = (
            os.environ.get("STAGING_ADMIN_TOKEN", "").strip()
            or os.environ.get("ADMIN_API_TOKEN_STAGING", "").strip()
        )
        if not token:
            raise RolloutError(
                "STAGING_ADMIN_TOKEN is required (or ADMIN_API_TOKEN_STAGING)"
            )
        return token
    token = (
        os.environ.get("PROD_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
    )
    if not token:
        raise RolloutError(
            "PROD_ADMIN_TOKEN is required (or ADMIN_API_TOKEN as production alias)"
        )
    return token


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def remaining_soak(started_at: float | None, soak_seconds: int) -> float:
    if not started_at:
        return float(soak_seconds)
    elapsed = time.time() - float(started_at)
    return max(0.0, float(soak_seconds) - elapsed)


def canary_percentage(payload: dict[str, Any]) -> int:
    """Parse canary percentage; treat missing as -1 (unknown)."""
    raw = payload.get("percentage")
    if raw is None:
        return -1
    return int(raw)


def assert_health(api_url: str) -> None:
    data = http_json(f"{api_url}/health", expected=200)
    if data.get("status") != "ok":
        raise RolloutError(f"health not ok: {data}")


def assert_openapi_paths(api_url: str, required: list[str]) -> None:
    """Fail fast when target image lacks Gate 10E / canary admin routes."""
    try:
        request = urllib.request.Request(
            f"{api_url}/openapi.json",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RolloutError(f"failed to load {api_url}/openapi.json: {exc}") from exc
    paths = payload.get("paths") if isinstance(payload, dict) else None
    if not isinstance(paths, dict):
        raise RolloutError(f"{api_url}/openapi.json missing paths")
    missing = [path for path in required if path not in paths]
    if missing:
        raise RolloutError(
            f"{api_url} missing routes {missing}. "
            "Deploy/pin Gate 10E+ images and Sync that environment first."
        )


def get_canary(api_url: str, token: str) -> dict[str, Any]:
    return http_json(f"{api_url}/admin/canary/status", token=token)


def set_canary(
    api_url: str,
    token: str,
    *,
    enabled: bool,
    percentage: int,
    features: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "enabled": enabled,
        "percentage": int(percentage),
    }
    if features is not None:
        body["features"] = features
    return http_json(
        f"{api_url}/admin/canary/config",
        method="POST",
        token=token,
        body=body,
    )


def get_safety(api_url: str, token: str) -> dict[str, Any]:
    return http_json(f"{api_url}/admin/safety/status", token=token)


def get_router(api_url: str, token: str) -> dict[str, Any]:
    return http_json(f"{api_url}/admin/router-status", token=token)


def get_abtest(api_url: str, token: str) -> dict[str, Any]:
    return http_json(f"{api_url}/admin/abtest/status", token=token)


def assert_prod_safety_env_off(api_url: str, token: str) -> dict[str, Any]:
    """Production must keep Gate 10E env flags off."""
    safety = get_safety(api_url, token)
    env = safety.get("env") or {}
    runtime = safety.get("runtime") or {}
    if env.get("feature_kill_switch") is True:
        raise RolloutError(
            "production FEATURE_KILL_SWITCH is true — refuse to continue "
            "(must stay false until explicit Gate 10E exit)"
        )
    if env.get("feature_auto_tuning") is True:
        raise RolloutError(
            "production FEATURE_AUTO_TUNING is true — refuse to continue"
        )
    if runtime.get("tripped") is True:
        raise RolloutError(
            f"production kill switch tripped: {runtime.get('trip_reason')}"
        )
    return safety


def production_smoke(repo_root: Path, api_url: str, web_url: str, token: str) -> None:
    python = os.environ.get("PYTHON") or str(repo_root / ".venv" / "bin" / "python")
    if not Path(python).exists():
        python = sys.executable
    env = os.environ.copy()
    env["ADMIN_API_TOKEN"] = token
    cmd = [
        python,
        str(repo_root / "scripts" / "production_smoke.py"),
        "--api-url",
        api_url,
        "--web-url",
        web_url,
        "--require-admin",
        "--allow-active-canary",
    ]
    log(f"$ {' '.join(cmd)} (ADMIN_API_TOKEN=*** )")
    import subprocess

    result = subprocess.run(
        cmd, cwd=str(repo_root), text=True, capture_output=True, env=env
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
    if result.returncode != 0:
        raise RolloutError(f"production_smoke failed (exit {result.returncode})")


def rollback_canary(api_url: str, token: str, *, reason: str) -> dict[str, Any]:
    log(f"==> ROLLBACK canary to 0% ({reason})")
    result = set_canary(api_url, token, enabled=False, percentage=0)
    log(
        "canary_rollback="
        f"enabled={result.get('enabled')} percentage={result.get('percentage')}"
    )
    return result


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def phase_staging_drill(
    *,
    staging_api: str,
    token: str,
    state: RolloutState,
    skip_cleanup: bool = False,
) -> StepResult:
    log("==> Phase staging_drill")
    assert_health(staging_api)
    assert_openapi_paths(
        staging_api,
        [
            "/admin/safety/status",
            "/admin/safety/kill/trip",
            "/admin/canary/status",
            "/admin/abtest/status",
        ],
    )

    # Confirm safety routes exist (Gate 10E image deployed on staging).
    try:
        before = get_safety(staging_api, token)
    except RolloutError as exc:
        raise RolloutError(
            "staging /admin/safety/* unavailable — deploy Gate 10E image to staging first "
            f"({exc})"
        ) from exc

    log(
        "staging_safety_before="
        f"env_kill={before.get('env', {}).get('feature_kill_switch')} "
        f"env_tune={before.get('env', {}).get('feature_auto_tuning')} "
        f"tripped={before.get('runtime', {}).get('tripped')}"
    )

    # Snapshot canary so we can restore after trip (trip zeros canary).
    canary_before = get_canary(staging_api, token)
    log(
        "staging_canary_before="
        f"enabled={canary_before.get('enabled')} "
        f"percentage={canary_before.get('percentage')}"
    )

    # Arm runtime flags for drill (works even if env is false — runtime overlay).
    http_json(
        f"{staging_api}/admin/safety/config",
        method="POST",
        token=token,
        body={
            "kill_switch_enabled": True,
            "auto_tune_enabled": True,
            "dry_run": True,
            "manual_override": False,
            "auto_tune_canary_enabled": False,
        },
    )

    # Put canary on so trip action zero_canary is observable.
    http_json(
        f"{staging_api}/admin/canary/config",
        method="POST",
        token=token,
        body={"enabled": True, "percentage": 5, "features": CANARY_FEATURES},
    )

    # Optional: start A/B so stop_abtest is observable (ignore if already off).
    ab_started = False
    try:
        started = http_json(
            f"{staging_api}/admin/abtest/start",
            method="POST",
            token=token,
            body={},
            expected=200,
        )
        ab_started = bool(started.get("running"))
        log(f"staging_abtest_started={ab_started}")
    except RolloutError as exc:
        log(f"staging_abtest_start_skipped ({exc})")

    trip = http_json(
        f"{staging_api}/admin/safety/kill/trip",
        method="POST",
        token=token,
        body={"reason": "gate10e_staging_drill", "force": True},
    )
    if not trip.get("tripped"):
        raise RolloutError(f"expected kill trip; got {trip}")

    canary_after_trip = get_canary(staging_api, token)
    # Note: do not use `percentage or -1` — 0 is a valid success value.
    if canary_percentage(canary_after_trip) != 0:
        raise RolloutError(f"kill trip did not zero canary: {canary_after_trip}")
    ab_after = get_abtest(staging_api, token)
    if ab_after.get("running") is True:
        raise RolloutError(f"kill trip did not stop A/B: {ab_after}")
    log("staging_kill_trip=ok (canary=0, abtest stopped)")

    disarm = http_json(
        f"{staging_api}/admin/safety/kill/disarm",
        method="POST",
        token=token,
        body={"clear_window": True},
    )
    if disarm.get("tripped") is True:
        raise RolloutError(f"disarm failed: {disarm}")

    # Re-arm auto-tune dry-run after trip disabled it.
    http_json(
        f"{staging_api}/admin/safety/config",
        method="POST",
        token=token,
        body={
            "kill_switch_enabled": True,
            "auto_tune_enabled": True,
            "dry_run": True,
            "manual_override": False,
        },
    )
    evaluate = http_json(
        f"{staging_api}/admin/safety/evaluate",
        method="POST",
        token=token,
        body={"force_tune": True},
    )
    tune = evaluate.get("tune") or {}
    log(f"staging_evaluate_tune={json.dumps(tune, sort_keys=True)[:400]}")

    audit = http_json(f"{staging_api}/admin/safety/audit?limit=10", token=token)
    events = audit.get("events") or []
    if not events:
        raise RolloutError("expected audit events after drill")
    log(f"staging_audit_events={len(events)}")

    if not skip_cleanup:
        # Leave staging safe: disarm flags, restore canary preference off.
        http_json(
            f"{staging_api}/admin/safety/config",
            method="POST",
            token=token,
            body={
                "kill_switch_enabled": False,
                "auto_tune_enabled": False,
                "manual_override": False,
                "dry_run": True,
            },
        )
        http_json(
            f"{staging_api}/admin/safety/kill/disarm",
            method="POST",
            token=token,
            body={"clear_window": True},
            expected=200,
        )
        # Prefer staging canary off after drill (safe default).
        set_canary(staging_api, token, enabled=False, percentage=0)
        if ab_started:
            http_json(
                f"{staging_api}/admin/abtest/stop",
                method="POST",
                token=token,
                body={},
                expected=200,
            )
        log("staging_cleanup=ok (safety disarmed, canary=0)")

    state.staging_drill_passed_at = time.time()
    state.note("staging_drill_passed", ab_started=ab_started)
    return StepResult("staging_drill", True, "trip+disarm+evaluate+audit ok")


def phase_c3(
    *,
    prod_api: str,
    prod_web: str,
    token: str,
    state: RolloutState,
    repo_root: Path,
    force: bool = False,
) -> StepResult:
    log("==> Phase c3 (canary 25%)")
    if not state.staging_drill_passed_at and not force:
        raise RolloutError(
            "staging_drill has not passed — run --phase staging_drill first "
            "(or --force to override)"
        )

    assert_health(prod_api)
    assert_openapi_paths(
        prod_api,
        ["/admin/safety/status", "/admin/canary/status"],
    )
    assert_prod_safety_env_off(prod_api, token)
    production_smoke(repo_root, prod_api, prod_web, token)

    before = get_canary(prod_api, token)
    pct = int(before.get("percentage") or 0)
    enabled = bool(before.get("enabled"))
    log(f"prod_canary_before=enabled={enabled} percentage={pct}")

    if enabled and pct == 25:
        state.c3_set_at = state.c3_set_at or time.time()
        state.c3_percentage = 25
        state.note("c3_already_set")
        return StepResult("c3", True, "already at 25%")

    if not force and not (enabled and pct == 5):
        raise RolloutError(
            f"expected production canary at C2 (5%) before C3; got "
            f"enabled={enabled} percentage={pct}. Use --force only with intent."
        )

    previous_pct = pct
    try:
        after = set_canary(
            prod_api,
            token,
            enabled=True,
            percentage=25,
            features=CANARY_FEATURES,
        )
        if canary_percentage(after) != 25 or not after.get("enabled"):
            raise RolloutError(f"failed to set C3: {after}")
        production_smoke(repo_root, prod_api, prod_web, token)
        assert_prod_safety_env_off(prod_api, token)
    except Exception as exc:
        rollback_canary(
            prod_api,
            token,
            reason=f"c3_failed:{exc.__class__.__name__}",
        )
        # Prefer restore to previous C2 if that was the prior state.
        if previous_pct == 5:
            try:
                set_canary(
                    prod_api,
                    token,
                    enabled=True,
                    percentage=5,
                    features=CANARY_FEATURES,
                )
                log("c3_failure_restored_c2=ok")
            except RolloutError:
                log("c3_failure_restore_c2=failed (left at 0)")
        raise

    state.c3_set_at = time.time()
    state.c3_percentage = 25
    state.note("c3_set", percentage=25)
    log("c3=ok percentage=25 (soak clock started)")
    return StepResult("c3", True, "canary=25%")


def phase_soak(
    *,
    label: str,
    started_at: float | None,
    soak_seconds: int,
    prod_api: str,
    token: str,
    expected_pct: int,
) -> StepResult:
    log(f"==> Phase soak_{label}")
    if not started_at:
        raise RolloutError(f"{label} not started — cannot soak")

    canary = get_canary(prod_api, token)
    pct = int(canary.get("percentage") or 0)
    if not canary.get("enabled") or pct != expected_pct:
        raise RolloutError(
            f"soak_{label}: expected canary {expected_pct}%, "
            f"got enabled={canary.get('enabled')} percentage={pct}"
        )
    assert_prod_safety_env_off(prod_api, token)

    left = remaining_soak(started_at, soak_seconds)
    elapsed = time.time() - float(started_at)
    log(
        f"soak_{label}="
        f"elapsed={fmt_duration(elapsed)} remaining={fmt_duration(left)} "
        f"required={fmt_duration(soak_seconds)}"
    )
    if left > 0:
        raise RolloutError(
            f"soak_{label} incomplete: {fmt_duration(left)} remaining "
            f"(re-run after soak; state file keeps the clock)"
        )
    return StepResult(f"soak_{label}", True, f"elapsed>={fmt_duration(soak_seconds)}")


def phase_c4(
    *,
    prod_api: str,
    prod_web: str,
    token: str,
    state: RolloutState,
    repo_root: Path,
    soak_seconds: int,
    force: bool = False,
) -> StepResult:
    log("==> Phase c4 (canary 100%)")
    if not force:
        left = remaining_soak(state.c3_set_at, soak_seconds)
        if left > 0:
            raise RolloutError(
                f"C3 soak incomplete ({fmt_duration(left)} left). "
                "Run --phase soak_c3 or wait."
            )

    assert_health(prod_api)
    assert_prod_safety_env_off(prod_api, token)
    production_smoke(repo_root, prod_api, prod_web, token)

    before = get_canary(prod_api, token)
    pct = int(before.get("percentage") or 0)
    if before.get("enabled") and pct == 100:
        state.c4_set_at = state.c4_set_at or time.time()
        state.c4_percentage = 100
        state.note("c4_already_set")
        return StepResult("c4", True, "already at 100%")

    if not force and pct != 25:
        raise RolloutError(f"expected C3 (25%) before C4; got percentage={pct}")

    previous_pct = pct
    try:
        after = set_canary(
            prod_api,
            token,
            enabled=True,
            percentage=100,
            features=CANARY_FEATURES,
        )
        if canary_percentage(after) != 100:
            raise RolloutError(f"failed to set C4: {after}")
        production_smoke(repo_root, prod_api, prod_web, token)
        assert_prod_safety_env_off(prod_api, token)
    except Exception as exc:
        rollback_canary(prod_api, token, reason=f"c4_failed:{exc.__class__.__name__}")
        if previous_pct == 25:
            try:
                set_canary(
                    prod_api,
                    token,
                    enabled=True,
                    percentage=25,
                    features=CANARY_FEATURES,
                )
                log("c4_failure_restored_c3=ok")
            except RolloutError:
                log("c4_failure_restore_c3=failed")
        raise

    state.c4_set_at = time.time()
    state.c4_percentage = 100
    state.note("c4_set", percentage=100)
    log("c4=ok percentage=100 (soak clock started)")
    return StepResult("c4", True, "canary=100%")


def phase_mock_router(
    *,
    prod_api: str,
    prod_web: str,
    token: str,
    state: RolloutState,
    repo_root: Path,
    soak_seconds: int,
    force: bool = False,
) -> StepResult:
    """After C4 soak: ensure canary 100% includes router → effective mock mode.

    Global FEATURE_AI_ROUTER stays false (env). Canary cohort at 100% activates
    router feature; effective_ai_router_mode maps disabled→mock for canary users.
    """
    log("==> Phase mock_router")
    if not force:
        left = remaining_soak(state.c4_set_at, soak_seconds)
        if left > 0:
            raise RolloutError(
                f"C4 soak incomplete ({fmt_duration(left)} left). "
                "Run --phase soak_c4 or wait."
            )

    assert_health(prod_api)
    assert_prod_safety_env_off(prod_api, token)
    production_smoke(repo_root, prod_api, prod_web, token)

    canary = get_canary(prod_api, token)
    pct = int(canary.get("percentage") or 0)
    features = list(canary.get("features") or [])
    if not canary.get("enabled") or pct != 100:
        raise RolloutError(
            f"mock_router requires C4 (100%); got enabled={canary.get('enabled')} pct={pct}"
        )
    if "router" not in features:
        log("adding router to canary features")
        canary = set_canary(
            prod_api,
            token,
            enabled=True,
            percentage=100,
            features=CANARY_FEATURES,
        )
        features = list(canary.get("features") or [])
    if "router" not in features:
        raise RolloutError(f"canary missing router feature: {features}")

    router = get_router(prod_api, token)
    # Global status may still show inactive when FEATURE_AI_ROUTER=false;
    # canary effective path enables mock per-request. Document clearly.
    log(
        "router_status="
        f"active={router.get('active')} mode={router.get('mode')} "
        f"(global flag may stay false; canary@100%+router ⇒ mock effective)"
    )
    log(
        "ACTION_OPTIONAL: To flip global env later: "
        "FEATURE_AI_ROUTER=true AI_ROUTER_MODE=mock + Render Sync "
        "(not done by this script — keeps env kill-switch discipline)."
    )

    state.mock_router_ready_at = time.time()
    state.note(
        "mock_router_ready",
        canary_percentage=pct,
        features=features,
        router_mode=router.get("mode"),
    )
    return StepResult(
        "mock_router",
        True,
        "canary=100% features include router (mock via canary effective mode)",
    )


def phase_status(
    *,
    staging_api: str,
    prod_api: str,
    state: RolloutState,
    soak_seconds: int,
) -> StepResult:
    log("==> Phase status")
    log(
        f"state_file_summary={json.dumps({k: v for k, v in asdict(state).items() if k != 'history'}, sort_keys=True)}"
    )
    if state.c3_set_at:
        log(
            f"c3_soak_remaining={fmt_duration(remaining_soak(state.c3_set_at, soak_seconds))}"
        )
    if state.c4_set_at:
        log(
            f"c4_soak_remaining={fmt_duration(remaining_soak(state.c4_set_at, soak_seconds))}"
        )

    for label, api, staging_flag in (
        ("staging", staging_api, True),
        ("production", prod_api, False),
    ):
        try:
            token = require_token(staging=staging_flag)
            assert_health(api)
            canary = get_canary(api, token)
            safety = get_safety(api, token)
            log(
                f"{label}_canary="
                f"enabled={canary.get('enabled')} percentage={canary.get('percentage')}"
            )
            log(
                f"{label}_safety="
                f"kill_env={safety.get('env', {}).get('feature_kill_switch')} "
                f"tune_env={safety.get('env', {}).get('feature_auto_tuning')} "
                f"tripped={safety.get('runtime', {}).get('tripped')}"
            )
        except RolloutError as exc:
            log(f"{label}_status_error={exc}")
    return StepResult("status", True, "reported")


def phase_rollback(
    *,
    prod_api: str,
    token: str,
    state: RolloutState,
) -> StepResult:
    log("==> Phase rollback")
    assert_health(prod_api)
    result = rollback_canary(prod_api, token, reason="operator_rollback")
    state.last_rollback_at = time.time()
    state.note("rollback", percentage=result.get("percentage"))
    return StepResult("rollback", True, "canary=0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate 10E staging drill + canary C3/C4 + mock router automation"
    )
    parser.add_argument("--phase", choices=PHASES, default="status")
    parser.add_argument(
        "--staging-api-url",
        default=os.environ.get("STAGING_API_URL", DEFAULT_STAGING_API),
    )
    parser.add_argument(
        "--prod-api-url", default=os.environ.get("API_URL", DEFAULT_PROD_API)
    )
    parser.add_argument(
        "--prod-web-url", default=os.environ.get("WEB_URL", DEFAULT_PROD_WEB)
    )
    parser.add_argument(
        "--state-file",
        default=str(
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "gate10e_rollout_state.json"
        ),
    )
    parser.add_argument(
        "--soak-seconds",
        type=int,
        default=int(os.environ.get("GATE10E_SOAK_SECONDS", str(DEFAULT_SOAK_SECONDS))),
        help="Minimum soak between canary advances (default 86400 = 24h)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass staging_drill / phase-precondition guards (dangerous)",
    )
    parser.add_argument(
        "--skip-staging-cleanup",
        action="store_true",
        help="Leave staging safety armed after drill (debug only)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    state_path = Path(args.state_file)
    state = RolloutState.load(state_path)
    soak_seconds = max(1, int(args.soak_seconds))
    steps: list[StepResult] = []

    staging_api = args.staging_api_url.rstrip("/")
    prod_api = args.prod_api_url.rstrip("/")
    prod_web = args.prod_web_url.rstrip("/")

    log(f"gate10e_rollout=start phase={args.phase} soak_seconds={soak_seconds}")
    log(f"state_file={state_path}")

    try:
        phases: list[str]
        if args.phase == "all":
            phases = [
                "staging_drill",
                "c3",
                "soak_c3",
                "c4",
                "soak_c4",
                "mock_router",
            ]
        else:
            phases = [args.phase]

        for phase in phases:
            if phase == "staging_drill":
                token = require_token(staging=True)
                steps.append(
                    phase_staging_drill(
                        staging_api=staging_api,
                        token=token,
                        state=state,
                        skip_cleanup=args.skip_staging_cleanup,
                    )
                )
            elif phase == "c3":
                token = require_token(staging=False)
                steps.append(
                    phase_c3(
                        prod_api=prod_api,
                        prod_web=prod_web,
                        token=token,
                        state=state,
                        repo_root=repo_root,
                        force=args.force,
                    )
                )
            elif phase == "soak_c3":
                token = require_token(staging=False)
                steps.append(
                    phase_soak(
                        label="c3",
                        started_at=state.c3_set_at,
                        soak_seconds=soak_seconds,
                        prod_api=prod_api,
                        token=token,
                        expected_pct=25,
                    )
                )
            elif phase == "c4":
                token = require_token(staging=False)
                steps.append(
                    phase_c4(
                        prod_api=prod_api,
                        prod_web=prod_web,
                        token=token,
                        state=state,
                        repo_root=repo_root,
                        soak_seconds=soak_seconds,
                        force=args.force,
                    )
                )
            elif phase == "soak_c4":
                token = require_token(staging=False)
                steps.append(
                    phase_soak(
                        label="c4",
                        started_at=state.c4_set_at,
                        soak_seconds=soak_seconds,
                        prod_api=prod_api,
                        token=token,
                        expected_pct=100,
                    )
                )
            elif phase == "mock_router":
                token = require_token(staging=False)
                steps.append(
                    phase_mock_router(
                        prod_api=prod_api,
                        prod_web=prod_web,
                        token=token,
                        state=state,
                        repo_root=repo_root,
                        soak_seconds=soak_seconds,
                        force=args.force,
                    )
                )
            elif phase == "status":
                steps.append(
                    phase_status(
                        staging_api=staging_api,
                        prod_api=prod_api,
                        state=state,
                        soak_seconds=soak_seconds,
                    )
                )
            elif phase == "rollback":
                token = require_token(staging=False)
                steps.append(
                    phase_rollback(prod_api=prod_api, token=token, state=state)
                )
            else:
                raise RolloutError(f"unknown phase: {phase}")

            state.save(state_path)

        log("gate10e_rollout=ok")
        for step in steps:
            log(f"step.{step.name}={'ok' if step.ok else 'FAIL'} detail={step.detail}")
        return 0
    except RolloutError as exc:
        state.note("error", message=str(exc), phase=args.phase)
        state.save(state_path)
        log(f"gate10e_rollout=error: {exc}")
        for step in steps:
            log(f"step.{step.name}={'ok' if step.ok else 'FAIL'} detail={step.detail}")
        return 1
    except Exception as exc:  # noqa: BLE001
        state.note("error", message=repr(exc), phase=args.phase)
        state.save(state_path)
        log(f"gate10e_rollout=error: unexpected {exc.__class__.__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
