#!/usr/bin/env python3
"""Gate 10I: arm FEATURE_KILL_SWITCH (staging drill → production).

Does not enable FEATURE_AUTO_TUNING (Gate 10J). Does not disable FEATURE_AI_ROUTER.

Kill switch env is Render Blueprint. Admin aliases:
  GET  /admin/kill-switch/status
  POST /admin/kill-switch/enable   (arm runtime; default trip → router fallback)
  POST /admin/kill-switch/disable  (disarm trip; optional unarm)

There is no Render Sync API in-repo — ``--stage *-sync`` prints operator steps.

Usage:
  export STAGING_ADMIN_TOKEN=...
  export PROD_ADMIN_TOKEN=...

  .venv/bin/python scripts/gate10i_kill_switch.py --stage check
  .venv/bin/python scripts/gate10i_kill_switch.py --stage staging-blueprint --dry-run
  .venv/bin/python scripts/gate10i_kill_switch.py --stage staging-blueprint --confirm-kill
  .venv/bin/python scripts/gate10i_kill_switch.py --stage staging-sync
  .venv/bin/python scripts/gate10i_kill_switch.py --stage staging-drill --assume-synced --confirm-trip
  .venv/bin/python scripts/gate10i_kill_switch.py --stage prod-blueprint --dry-run
  .venv/bin/python scripts/gate10i_kill_switch.py --stage prod-blueprint --confirm-kill
  .venv/bin/python scripts/gate10i_kill_switch.py --stage prod-sync
  .venv/bin/python scripts/gate10i_kill_switch.py --stage prod-verify --assume-synced
  .venv/bin/python scripts/gate10i_kill_switch.py --stage monitor --target prod
  .venv/bin/python scripts/gate10i_kill_switch.py --stage prod-drill --confirm-trip
  .venv/bin/python scripts/gate10i_kill_switch.py --stage rollback --target prod --confirm-rollback
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STAGING = "https://dealhunter-staging-api.onrender.com"
DEFAULT_PROD = "https://dealhunter-production-api.onrender.com"
USER_AGENT = "SaveIQ-Gate10I-KillSwitch/1.0"
HTTP_RE = re.compile(
    r'^http_requests_total\{(?P<labels>[^}]*)\}\s+(?P<val>[0-9.eE+-]+)\s*$'
)
STAGES = (
    "check",
    "staging-blueprint",
    "staging-sync",
    "staging-drill",
    "prod-blueprint",
    "prod-sync",
    "prod-verify",
    "prod-drill",
    "monitor",
    "rollback",
)


def canary_percentage(payload: dict[str, Any]) -> int:
    """0 is a valid canary value — never use `percentage or -1`."""
    raw = payload.get("percentage")
    if raw is None:
        return -1
    return int(raw)


class Gate10IError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def assert_http_token(token: str, *, name: str) -> str:
    """HTTP headers must be latin-1. Vietnamese placeholder text will crash urllib."""
    cleaned = token.strip()
    if not cleaned:
        raise Gate10IError(f"{name} is empty")
    if cleaned in {"...", "…"} or "token" in cleaned.lower() and not cleaned.isascii():
        raise Gate10IError(
            f"{name} looks like a placeholder (contains Vietnamese/non-ASCII). "
            "Paste the exact ADMIN_API_TOKEN from Render Environment — hex only, no comments."
        )
    try:
        cleaned.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise Gate10IError(
            f"{name} has non-ASCII characters (e.g. Vietnamese). "
            "Re-export the Render ADMIN_API_TOKEN value only, no comments on the same line."
        ) from exc
    return cleaned


def http_json(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["X-Admin-Token"] = assert_http_token(token, name="X-Admin-Token")
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if exc.code == 401:
            host = "STAGING_ADMIN_TOKEN" if "staging" in url else "PROD_ADMIN_TOKEN"
            hint = f" (wrong/missing admin token — set {host})"
        raise Gate10IError(f"{method} {url} -> HTTP {exc.code}: {err[:400]}{hint}") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        hint = ""
        if "staging" in url:
            hint = (
                " — staging API did not respond in 120s. Resume "
                "dealhunter-staging-postgres if Suspended, wait until "
                "dealhunter-staging-api is Live, then: "
                "curl -sS --max-time 30 "
                "https://dealhunter-staging-api.onrender.com/health"
            )
        raise Gate10IError(f"{method} {url} timed out ({exc}){hint}") from exc
    parsed = json.loads(payload) if payload else {}
    if not isinstance(parsed, dict):
        raise Gate10IError(f"{url} did not return a JSON object")
    return parsed


def http_json_or_404(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        return http_json(url, token=token, method=method, body=body)
    except Gate10IError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def http_text(url: str, *, token: str | None = None) -> str:
    headers = {"Accept": "text/plain", "User-Agent": USER_AGENT}
    metrics_token = os.environ.get("METRICS_TOKEN", "").strip()
    if metrics_token:
        headers["X-Metrics-Token"] = metrics_token
    if token:
        headers["X-Admin-Token"] = assert_http_token(token, name="X-Admin-Token")
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise Gate10IError(f"GET {url} -> HTTP {exc.code}: {err[:200]}") from exc


def parse_http_5xx(text: str) -> float:
    total = 0.0
    for line in text.splitlines():
        match = HTTP_RE.match(line.strip())
        if not match:
            continue
        if 'status_code="5' in match.group("labels"):
            total += float(match.group("val"))
    return total


def require_staging_token() -> str:
    token = (
        os.environ.get("STAGING_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
    )
    if not token:
        raise Gate10IError("STAGING_ADMIN_TOKEN required (staging ADMIN_API_TOKEN)")
    return assert_http_token(token, name="STAGING_ADMIN_TOKEN")


def require_prod_token() -> str:
    token = os.environ.get("PROD_ADMIN_TOKEN", "").strip()
    if not token:
        raise Gate10IError("PROD_ADMIN_TOKEN required (production ADMIN_API_TOKEN)")
    return assert_http_token(token, name="PROD_ADMIN_TOKEN")


def blueprint_get(text: str, key: str) -> str | None:
    match = re.search(
        rf'(?m)^(\s+- key: {re.escape(key)}\n\s+value:\s*)(?:"([^"]*)"|([^\s#]+))',
        text,
    )
    if not match:
        return None
    return match.group(2) if match.group(2) is not None else match.group(3)


def blueprint_set(text: str, key: str, value: str) -> str:
    pattern = re.compile(
        rf'(?m)^(\s+- key: {re.escape(key)}\n\s+value:\s*)(?:"([^"]*)"|([^\s#]+))'
    )

    def _repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        if match.group(2) is not None:
            return f'{prefix}"{value}"'
        return f"{prefix}{value}"

    new_text, n = pattern.subn(_repl, text, count=1)
    if n != 1:
        raise Gate10IError(f"failed to set {key} in Blueprint (matches={n})")
    return new_text


def apply_kill_blueprint(path: Path, *, enabled: bool, dry_run: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    before = {
        "FEATURE_KILL_SWITCH": blueprint_get(text, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text, "FEATURE_AUTO_TUNING"),
        "FEATURE_AI_ROUTER": blueprint_get(text, "FEATURE_AI_ROUTER"),
        "FEATURE_NEURAL_BANDIT": blueprint_get(text, "FEATURE_NEURAL_BANDIT"),
        "FEATURE_RLHF_ROUTER": blueprint_get(text, "FEATURE_RLHF_ROUTER"),
    }
    text2 = blueprint_set(text, "FEATURE_KILL_SWITCH", "true" if enabled else "false")
    text2 = blueprint_set(text2, "FEATURE_AUTO_TUNING", "false")
    after = {
        "FEATURE_KILL_SWITCH": blueprint_get(text2, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text2, "FEATURE_AUTO_TUNING"),
        "FEATURE_AI_ROUTER": blueprint_get(text2, "FEATURE_AI_ROUTER"),
        "FEATURE_NEURAL_BANDIT": blueprint_get(text2, "FEATURE_NEURAL_BANDIT"),
        "FEATURE_RLHF_ROUTER": blueprint_get(text2, "FEATURE_RLHF_ROUTER"),
    }
    if after["FEATURE_AUTO_TUNING"] != "false":
        raise Gate10IError("FEATURE_AUTO_TUNING must stay false (Gate 10J)")
    if after["FEATURE_AI_ROUTER"] != before["FEATURE_AI_ROUTER"]:
        raise Gate10IError("refusing to change FEATURE_AI_ROUTER")
    if dry_run:
        log(f"blueprint_dry_run path={path}")
        log(f"blueprint_dry_run before={json.dumps(before, sort_keys=True)}")
        log(f"blueprint_dry_run after={json.dumps(after, sort_keys=True)}")
        log("blueprint_dry_run=ok (no write)")
    else:
        path.write_text(text2, encoding="utf-8")
        log(f"blueprint_updated={path}")
        log(f"blueprint_after={json.dumps(after, sort_keys=True)}")
    return {"before": before, "after": after, "changed": text2 != text, "dry_run": dry_run}


def validate_blueprint(
    repo: Path,
    python: str,
    blueprint: Path,
    *,
    production: bool,
    kill_on: bool,
) -> None:
    cmd = [python, str(repo / "scripts" / "validate_render_blueprint.py"), str(blueprint)]
    if production:
        cmd.extend(["--profile", "production", "--allow-live-ai"])
        cmd.append("--allow-neural-bandit")
        cmd.append("--allow-rlhf-router")
        cmd.append("--allow-rlhf-after-neural")
        if kill_on:
            cmd.append("--allow-kill-switch")
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        raise Gate10IError(f"{blueprint.name} validation failed")


def print_sync_steps(*, production: bool) -> None:
    name = "production" if production else "staging"
    yaml_name = "render-production.yaml" if production else "render.yaml"
    log(f"ACTION_REQUIRED: Sync {name} Blueprint ({yaml_name})")
    log("  1) Commit/PR the FEATURE_KILL_SWITCH=true change (autotune stays false)")
    log("  2) Render Dashboard → Blueprint → Sync (or wait for autoDeploy if on)")
    log("  3) Confirm env FEATURE_KILL_SWITCH=true on the API service")
    if production:
        log("  4) After merge, CI `production-provision-validate` needs --allow-kill-switch")
        log("  5) make gate10i-kill-switch ARGS='--stage prod-verify --assume-synced'")
    else:
        log("  4) make gate10i-kill-switch ARGS='--stage staging-drill --assume-synced --confirm-trip'")


class Gate10I:
    def __init__(
        self,
        *,
        repo: Path,
        staging_api: str,
        prod_api: str,
        staging_blueprint: Path,
        prod_blueprint: Path,
        state_path: Path,
        dry_run: bool,
        python: str,
        report_dir: Path,
        skip_10h: bool,
        unarm_after_drill: bool,
    ) -> None:
        self.repo = repo
        self.staging_api = staging_api.rstrip("/")
        self.prod_api = prod_api.rstrip("/")
        self.staging_bp = staging_blueprint
        self.prod_bp = prod_blueprint
        self.state_path = state_path
        self.dry_run = dry_run
        self.python = python
        self.report_dir = report_dir
        self.skip_10h = skip_10h
        self.unarm_after_drill = unarm_after_drill
        self.results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gate": "10I_kill_switch",
            "dry_run": dry_run,
            "checks": [],
        }

    def _note(self, name: str, ok: bool, message: str) -> bool:
        status = "PASS" if ok else "FAIL"
        log(f"  {name}: {status} — {message}")
        self.results["checks"].append({"step": name, "status": status, "message": message})
        return ok

    def load_state(self) -> dict[str, Any]:
        return load_json(self.state_path)

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(self.state_path, state)
        log(f"state_written={self.state_path}")

    def check(self) -> bool:
        log("gate10i=check")
        ok = True
        if self.skip_10h:
            ok &= self._note("gate10h", True, "skipped (--skip-10h)")
        else:
            token = require_prod_token()
            bandit = http_json(f"{self.prod_api}/admin/bandit/status", token=token)
            flags = bandit.get("flags") or {}
            ok &= self._note(
                "gate10h_flags",
                flags.get("neural") is True and flags.get("rlhf") is True,
                f"flags={flags} policy={bandit.get('policy')}",
            )
            rlhf_state = load_json(self.repo / "artifacts" / "gate10h_prod_rlhf_state.json")
            promoted = bool(rlhf_state.get("promoted_at"))
            soak = load_json(self.repo / "artifacts" / "gate10h_soak_report_n100_latest.json")
            soak_ok = str(soak.get("status") or "").upper() == "PASS"
            if rlhf_state or soak:
                ok &= self._note(
                    "gate10h_artifacts",
                    promoted or soak_ok,
                    f"promoted_at={rlhf_state.get('promoted_at')} soak={soak.get('status')}",
                )
            else:
                ok &= self._note(
                    "gate10h_artifacts",
                    True,
                    "no local artifacts; live flags used",
                )
            safety = http_json(f"{self.prod_api}/admin/safety/status", token=token)
            env = safety.get("env") or {}
            runtime = safety.get("runtime") or {}
            ok &= self._note(
                "prod_autotune_off",
                env.get("feature_auto_tuning") is not True,
                f"autotune={env.get('feature_auto_tuning')}",
            )
            ok &= self._note(
                "prod_not_tripped",
                runtime.get("tripped") is not True,
                f"tripped={runtime.get('tripped')} kill={env.get('feature_kill_switch')}",
            )
        log(f"gate10i=check {'ok' if ok else 'error'}")
        return ok

    def _blueprint_stage(self, *, production: bool, confirm: bool) -> bool:
        path = self.prod_bp if production else self.staging_bp
        label = "prod" if production else "staging"
        log(f"gate10i={label}-blueprint")
        dry = self.dry_run or not confirm
        if not confirm and not self.dry_run:
            log("pass --confirm-kill to write Blueprint (or --dry-run)")
            dry = True
        result = apply_kill_blueprint(path, enabled=True, dry_run=dry)
        on_disk = (
            blueprint_get(path.read_text(encoding="utf-8"), "FEATURE_KILL_SWITCH") == "true"
        )
        validate_blueprint(
            self.repo,
            self.python,
            path,
            production=production,
            kill_on=on_disk,
        )
        if dry:
            log(f"{label}_blueprint=dry-run ok")
            return True
        state = self.load_state()
        state[f"{label}_blueprint"] = result["after"]
        state[f"{label}_blueprint_at"] = datetime.now(timezone.utc).isoformat()
        self.save_state(state)
        log(f"{label}_blueprint=ok FEATURE_KILL_SWITCH=true FEATURE_AUTO_TUNING=false")
        return True

    def staging_blueprint(self, *, confirm: bool) -> bool:
        return self._blueprint_stage(production=False, confirm=confirm)

    def prod_blueprint(self, *, confirm: bool) -> bool:
        return self._blueprint_stage(production=True, confirm=confirm)

    def staging_sync(self) -> bool:
        print_sync_steps(production=False)
        return True

    def prod_sync(self) -> bool:
        print_sync_steps(production=True)
        return True

    def _snapshot_canary(self, api: str, token: str) -> dict[str, Any]:
        return http_json(f"{api}/admin/canary/status", token=token)

    def _kill_status_from_safety(self, api: str, token: str) -> dict[str, Any]:
        safety = http_json(f"{api}/admin/safety/status", token=token)
        runtime = safety.get("runtime") or {}
        env = safety.get("env") or {}
        tripped = bool(runtime.get("tripped"))
        router = http_json(f"{api}/admin/router-status", token=token)
        return {
            "env_flag": bool(env.get("feature_kill_switch")),
            "armed": bool(runtime.get("kill_switch_enabled")),
            "tripped": tripped,
            "trip_reason": runtime.get("trip_reason"),
            "trip_at": runtime.get("trip_at"),
            "manual_override": bool(runtime.get("manual_override")),
            "auto_tune_enabled": bool(runtime.get("auto_tune_enabled")),
            "router_fallback": tripped,
            "request_router_active": bool(router.get("request_router_active", router.get("active"))),
            "legacy_safety_api": True,
            "safety": safety,
        }

    def _require_kill_paths(self, api: str, token: str) -> dict[str, Any]:
        status = http_json_or_404(f"{api}/admin/kill-switch/status", token=token)
        if status is not None and "tripped" in status:
            status["legacy_safety_api"] = False
            return status
        log("WARN: /admin/kill-switch/* missing — using /admin/safety/kill/* (pre-10I image)")
        return self._kill_status_from_safety(api, token)

    def _trip_kill(self, api: str, token: str, *, reason: str, legacy: bool) -> dict[str, Any]:
        if not legacy:
            return http_json(
                f"{api}/admin/kill-switch/enable",
                token=token,
                method="POST",
                body={"reason": reason, "trip": True, "force": True},
            )
        http_json(
            f"{api}/admin/safety/config",
            token=token,
            method="POST",
            body={
                "kill_switch_enabled": True,
                "manual_override": False,
                "auto_tune_enabled": False,
            },
        )
        trip = http_json(
            f"{api}/admin/safety/kill/trip",
            token=token,
            method="POST",
            body={"reason": reason, "force": True},
        )
        merged = self._kill_status_from_safety(api, token)
        merged["trip"] = trip
        merged["tripped"] = bool(trip.get("tripped", merged["tripped"]))
        merged["router_fallback"] = bool(merged["tripped"])
        return merged

    def _disarm_kill(self, api: str, token: str, *, legacy: bool) -> dict[str, Any]:
        if not legacy:
            return http_json(
                f"{api}/admin/kill-switch/disable",
                token=token,
                method="POST",
                body={"clear_window": True, "unarm": self.unarm_after_drill},
            )
        disarm = http_json(
            f"{api}/admin/safety/kill/disarm",
            token=token,
            method="POST",
            body={"clear_window": True},
        )
        if self.unarm_after_drill:
            http_json(
                f"{api}/admin/safety/config",
                token=token,
                method="POST",
                body={"kill_switch_enabled": False, "auto_tune_enabled": False},
            )
        merged = self._kill_status_from_safety(api, token)
        merged["disarm"] = disarm
        return merged

    def _restore_canary(self, api: str, token: str, snapshot: dict[str, Any]) -> None:
        enabled = bool(snapshot.get("enabled"))
        percentage = canary_percentage(snapshot)
        if percentage < 0:
            percentage = 0
        features = snapshot.get("features") or ["router", "bandit", "personalization", "llm_cn"]
        http_json(
            f"{api}/admin/canary/config",
            token=token,
            method="POST",
            body={"enabled": enabled, "percentage": percentage, "features": features},
        )
        log(f"canary_restored enabled={enabled} percentage={percentage}")

    def _drill(
        self,
        *,
        api: str,
        token: str,
        reason: str,
        confirm: bool,
        assume_synced: bool,
        restore_canary: bool,
        require_env_flag: bool,
    ) -> bool:
        if not confirm:
            raise Gate10IError("refusing trip without --confirm-trip")
        if self.dry_run:
            log("[DRY RUN] would POST /admin/kill-switch/enable trip=true then disable")
            return True
        ks = self._require_kill_paths(api, token)
        legacy = bool(ks.get("legacy_safety_api"))
        env_flag = bool(ks.get("env_flag"))
        if require_env_flag and not env_flag:
            if assume_synced:
                raise Gate10IError(
                    "FEATURE_KILL_SWITCH env is still false after --assume-synced. "
                    "Render → dealhunter-staging-api → Environment: set/Sync the flag, "
                    "or rerun without --assume-synced to drill the runtime overlay only."
                )
            raise Gate10IError("FEATURE_KILL_SWITCH env is false — Sync Blueprint first")
        canary_before = self._snapshot_canary(api, token)
        router_before = http_json(f"{api}/admin/router-status", token=token)
        log(
            f"drill_before env_flag={env_flag} armed={ks.get('armed')} "
            f"tripped={ks.get('tripped')} legacy={legacy} "
            f"request_router_active={ks.get('request_router_active')} "
            f"canary={canary_percentage(canary_before)}"
        )
        if canary_percentage(canary_before) == 0:
            log("drill_seed_canary=5 so zero_canary is observable")
            http_json(
                f"{api}/admin/canary/config",
                token=token,
                method="POST",
                body={
                    "enabled": True,
                    "percentage": 5,
                    "features": canary_before.get("features")
                    or ["router", "bandit", "personalization", "llm_cn"],
                },
            )
            seeded = self._snapshot_canary(api, token)
            if canary_percentage(seeded) != 5:
                raise Gate10IError(f"failed to seed canary to 5%: {seeded}")
        enabled = self._trip_kill(api, token, reason=reason, legacy=legacy)
        if not enabled.get("tripped"):
            raise Gate10IError(f"enable/trip failed: {enabled}")
        if not legacy and not enabled.get("router_fallback"):
            raise Gate10IError(f"enable/trip failed: {enabled}")
        if not legacy and enabled.get("request_router_active") is not False:
            raise Gate10IError(
                f"expected request_router_active=false after trip; got {enabled}"
            )
        canary_after = self._snapshot_canary(api, token)
        if canary_percentage(canary_after) != 0:
            raise Gate10IError(f"kill trip did not zero canary: {canary_after}")
        log("drill_trip=ok (canary=0" + ("" if legacy else " + router fallback") + ")")
        disabled = self._disarm_kill(api, token, legacy=legacy)
        if disabled.get("tripped") is True:
            raise Gate10IError(f"disable failed: {disabled}")
        if disabled.get("request_router_active") is False and router_before.get(
            "request_router_active"
        ):
            log("WARN: request_router_active still false after disarm (check canary/flags)")
        if restore_canary:
            self._restore_canary(api, token, canary_before)
        audit = http_json(f"{api}/admin/safety/audit?limit=10", token=token)
        events = audit.get("events") or []
        if not events:
            raise Gate10IError("expected safety audit events after drill")
        log(f"drill_audit_events={len(events)}")
        return True

    def staging_drill(self, *, confirm: bool, assume_synced: bool) -> bool:
        log("gate10i=staging-drill")
        token = require_staging_token()
        ok = self._drill(
            api=self.staging_api,
            token=token,
            reason="gate10i_staging_drill",
            confirm=confirm,
            assume_synced=assume_synced,
            restore_canary=True,
            require_env_flag=assume_synced,
        )
        state = self.load_state()
        state["staging_drill_passed_at"] = datetime.now(timezone.utc).isoformat()
        self.save_state(state)
        log("gate10i=staging-drill ok")
        return ok

    def prod_verify(self, *, assume_synced: bool) -> bool:
        log("gate10i=prod-verify")
        if not assume_synced:
            raise Gate10IError("pass --assume-synced after Render Sync")
        token = require_prod_token()
        ok = True
        ks = self._require_kill_paths(self.prod_api, token)
        ok &= self._note("env_flag", ks.get("env_flag") is True, f"env_flag={ks.get('env_flag')}")
        ok &= self._note("armed", ks.get("armed") is True, f"armed={ks.get('armed')}")
        ok &= self._note(
            "not_tripped",
            ks.get("tripped") is not True,
            f"tripped={ks.get('tripped')}",
        )
        ok &= self._note(
            "autotune_off",
            ks.get("auto_tune_enabled") is not True,
            f"auto_tune={ks.get('auto_tune_enabled')}",
        )
        ok &= self._note(
            "router_live",
            ks.get("request_router_active") is True,
            f"request_router_active={ks.get('request_router_active')}",
        )
        safety = ks.get("safety") or {}
        env = safety.get("env") or {}
        ok &= self._note(
            "env_autotune",
            env.get("feature_auto_tuning") is not True,
            f"env_autotune={env.get('feature_auto_tuning')}",
        )
        state = self.load_state()
        state["prod_verified_at"] = datetime.now(timezone.utc).isoformat()
        state["prod_kill_status"] = {
            "env_flag": ks.get("env_flag"),
            "armed": ks.get("armed"),
            "tripped": ks.get("tripped"),
        }
        self.save_state(state)
        log(f"gate10i=prod-verify {'ok' if ok else 'error'}")
        return ok

    def prod_drill(self, *, confirm: bool) -> bool:
        log("gate10i=prod-drill")
        log("WARNING: production trip zeros canary and forces AI router fallback")
        token = require_prod_token()
        ok = self._drill(
            api=self.prod_api,
            token=token,
            reason="gate10i_prod_drill",
            confirm=confirm,
            assume_synced=True,
            restore_canary=True,
            require_env_flag=True,
        )
        state = self.load_state()
        state["prod_drill_passed_at"] = datetime.now(timezone.utc).isoformat()
        self.save_state(state)
        log("gate10i=prod-drill ok (canary restored, trip cleared)")
        return ok

    def monitor(self, *, target: str) -> bool:
        log(f"gate10i=monitor target={target}")
        production = target == "prod"
        api = self.prod_api if production else self.staging_api
        token = require_prod_token() if production else require_staging_token()
        ok = True
        ks = self._require_kill_paths(api, token)
        ok &= self._note(
            "not_tripped",
            ks.get("tripped") is not True,
            f"tripped={ks.get('tripped')} reason={ks.get('trip_reason')}",
        )
        ok &= self._note(
            "autotune_off",
            ks.get("auto_tune_enabled") is not True,
            f"auto_tune={ks.get('auto_tune_enabled')}",
        )
        try:
            metrics = http_text(f"{api}/metrics", token=token)
            five = parse_http_5xx(metrics)
            ok &= self._note("http_5xx", five == 0.0, f"cumulative_5xx={five:.0f}")
        except Gate10IError as exc:
            ok &= self._note("http_5xx", True, f"skipped ({exc})")
        log(f"gate10i=monitor {'ok' if ok else 'error'}")
        return ok

    def rollback(self, *, target: str, confirm: bool) -> bool:
        log(f"gate10i=rollback target={target}")
        if not confirm:
            raise Gate10IError("refusing rollback without --confirm-rollback")
        production = target == "prod"
        api = self.prod_api if production else self.staging_api
        token = require_prod_token() if production else require_staging_token()
        path = self.prod_bp if production else self.staging_bp
        if self.dry_run:
            log("[DRY RUN] would disable trip + FEATURE_KILL_SWITCH=false (AI router unchanged)")
            apply_kill_blueprint(path, enabled=False, dry_run=True)
            return True
        http_json(
            f"{api}/admin/kill-switch/disable",
            token=token,
            method="POST",
            body={"clear_window": True, "unarm": True},
        )
        result = apply_kill_blueprint(path, enabled=False, dry_run=False)
        validate_blueprint(
            self.repo,
            self.python,
            path,
            production=production,
            kill_on=False,
        )
        state = self.load_state()
        state["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
        state["rollback_target"] = target
        state["rollback_blueprint"] = result["after"]
        self.save_state(state)
        log("ACTION_REQUIRED: Sync Blueprint so FEATURE_KILL_SWITCH=false is durable")
        log("rollback=ok (FEATURE_AI_ROUTER left unchanged; autotune left false)")
        return True

    def write_report(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.report_dir / f"gate10i_kill_switch_{stamp}.json"
        save_json(path, self.results)
        save_json(self.report_dir / "gate10i_kill_switch_latest.json", self.results)
        log(f"report_written={path}")
        return path


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10I kill switch enablement")
    parser.add_argument("--stage", choices=STAGES, default="check")
    parser.add_argument("--target", choices=["staging", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--confirm-kill", action="store_true")
    parser.add_argument("--confirm-trip", action="store_true")
    parser.add_argument("--confirm-rollback", action="store_true")
    parser.add_argument("--assume-synced", action="store_true")
    parser.add_argument("--skip-10h", action="store_true")
    parser.add_argument(
        "--unarm-after-drill",
        action="store_true",
        help="After drill, set runtime kill_switch_enabled=false (default: leave armed)",
    )
    parser.add_argument("--staging-api", default=os.environ.get("STAGING_API_URL", DEFAULT_STAGING))
    parser.add_argument("--prod-api", default=os.environ.get("API_URL", DEFAULT_PROD))
    parser.add_argument("--staging-blueprint", default=str(repo / "render.yaml"))
    parser.add_argument("--prod-blueprint", default=str(repo / "render-production.yaml"))
    parser.add_argument(
        "--state-file",
        default=str(repo / "artifacts" / "gate10i_kill_switch_state.json"),
    )
    parser.add_argument("--report-dir", default=str(repo / "artifacts"))
    parser.add_argument("--python", default="")
    parser.add_argument("--repo-root", default=str(repo))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root)
    python = args.python or os.environ.get("PYTHON") or str(repo / ".venv" / "bin" / "python")
    if not Path(python).exists():
        python = sys.executable
    runner = Gate10I(
        repo=repo,
        staging_api=args.staging_api,
        prod_api=args.prod_api,
        staging_blueprint=Path(args.staging_blueprint),
        prod_blueprint=Path(args.prod_blueprint),
        state_path=Path(args.state_file),
        dry_run=args.dry_run,
        python=python,
        report_dir=Path(args.report_dir),
        skip_10h=args.skip_10h,
        unarm_after_drill=args.unarm_after_drill,
    )
    log(f"gate10i=start stage={args.stage} dry_run={args.dry_run}")
    try:
        ok = False
        if args.stage == "check":
            ok = runner.check()
        elif args.stage == "staging-blueprint":
            ok = runner.staging_blueprint(confirm=args.confirm_kill)
        elif args.stage == "staging-sync":
            ok = runner.staging_sync()
        elif args.stage == "staging-drill":
            ok = runner.staging_drill(confirm=args.confirm_trip, assume_synced=args.assume_synced)
        elif args.stage == "prod-blueprint":
            ok = runner.prod_blueprint(confirm=args.confirm_kill)
        elif args.stage == "prod-sync":
            ok = runner.prod_sync()
        elif args.stage == "prod-verify":
            ok = runner.prod_verify(assume_synced=args.assume_synced)
        elif args.stage == "prod-drill":
            ok = runner.prod_drill(confirm=args.confirm_trip)
        elif args.stage == "monitor":
            ok = runner.monitor(target=args.target)
        elif args.stage == "rollback":
            ok = runner.rollback(target=args.target, confirm=args.confirm_rollback)
        if args.report:
            runner.results["ok"] = ok
            runner.write_report()
        log(f"gate10i={args.stage} {'ok' if ok else 'error'}")
        return 0 if ok else 1
    except Gate10IError as exc:
        log(f"gate10i=error {exc}")
        if args.report:
            runner.results["ok"] = False
            runner.results["error"] = str(exc)
            runner.write_report()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
