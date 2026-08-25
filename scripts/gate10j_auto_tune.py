#!/usr/bin/env python3
"""Gate 10J: staging-only auto-tune dry-run scaffold.

Does **not** enable FEATURE_AUTO_TUNING in production.
Does **not** mutate FEATURE_NEURAL_BANDIT, FEATURE_RLHF_ROUTER, or BANDIT_POLICY.

Durable env is Render Blueprint. This script only writes ``render.yaml`` (staging).
Runtime overlay (POST /admin/safety/config) can arm dry-run evaluate before Sync.

Usage:
  export STAGING_ADMIN_TOKEN=...
  export PROD_ADMIN_TOKEN=...

  .venv/bin/python scripts/gate10j_auto_tune.py --stage check
  .venv/bin/python scripts/gate10j_auto_tune.py --stage staging-dry-run
  .venv/bin/python scripts/gate10j_auto_tune.py --stage staging-dry-run --confirm-autotune
  .venv/bin/python scripts/gate10j_auto_tune.py --stage evaluate
  .venv/bin/python scripts/gate10j_auto_tune.py --stage evaluate --confirm-autotune
  .venv/bin/python scripts/gate10j_auto_tune.py --stage cleanup --confirm-autotune
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
USER_AGENT = "SaveIQ-Gate10J-AutoTune/1.0"
STAGES = ("check", "staging-dry-run", "evaluate", "cleanup")
HUMAN_ONLY_KEYS = ("FEATURE_NEURAL_BANDIT", "FEATURE_RLHF_ROUTER", "BANDIT_POLICY")
PROPOSE_EVENTS = {"autotune_propose"}
APPLY_EVENTS = {"hparams_update", "autotune_canary"}


class Gate10JError(RuntimeError):
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
        raise Gate10JError(f"{name} is empty")
    looks_placeholder = cleaned in {"...", "…"} or (
        "token" in cleaned.lower() and not cleaned.isascii()
    )
    if looks_placeholder:
        raise Gate10JError(
            f"{name} looks like a placeholder (contains Vietnamese/non-ASCII). "
            "Paste the exact ADMIN_API_TOKEN from Render Environment — hex only, no comments."
        )
    try:
        cleaned.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise Gate10JError(
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
        raise Gate10JError(f"{method} {url} -> HTTP {exc.code}: {err[:400]}{hint}") from exc
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
        raise Gate10JError(f"{method} {url} timed out ({exc}){hint}") from exc
    parsed = json.loads(payload) if payload else {}
    if not isinstance(parsed, dict):
        raise Gate10JError(f"{url} did not return a JSON object")
    return parsed


def require_staging_token() -> str:
    token = (
        os.environ.get("STAGING_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
    )
    if not token:
        raise Gate10JError("STAGING_ADMIN_TOKEN required (staging ADMIN_API_TOKEN)")
    return assert_http_token(token, name="STAGING_ADMIN_TOKEN")


def require_prod_token() -> str:
    token = os.environ.get("PROD_ADMIN_TOKEN", "").strip()
    if not token:
        raise Gate10JError("PROD_ADMIN_TOKEN required (production ADMIN_API_TOKEN)")
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
        raise Gate10JError(f"failed to set {key} in Blueprint (matches={n})")
    return new_text


def assert_staging_blueprint(path: Path) -> None:
    name = path.name.lower()
    if "production" in name:
        raise Gate10JError(
            f"refusing to mutate production Blueprint {path.name} (Gate 10J staging-only)"
        )


def snapshot_human_only(text: str) -> dict[str, str | None]:
    return {key: blueprint_get(text, key) for key in HUMAN_ONLY_KEYS}


def apply_staging_autotune_blueprint(
    path: Path,
    *,
    enabled: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Set FEATURE_AUTO_TUNING on staging Blueprint. AUTO_TUNE_DRY_RUN stays true."""
    assert_staging_blueprint(path)
    text = path.read_text(encoding="utf-8")
    before = {
        "FEATURE_AUTO_TUNING": blueprint_get(text, "FEATURE_AUTO_TUNING"),
        "AUTO_TUNE_DRY_RUN": blueprint_get(text, "AUTO_TUNE_DRY_RUN"),
        **snapshot_human_only(text),
    }
    text2 = blueprint_set(text, "FEATURE_AUTO_TUNING", "true" if enabled else "false")
    text2 = blueprint_set(text2, "AUTO_TUNE_DRY_RUN", "true")
    after = {
        "FEATURE_AUTO_TUNING": blueprint_get(text2, "FEATURE_AUTO_TUNING"),
        "AUTO_TUNE_DRY_RUN": blueprint_get(text2, "AUTO_TUNE_DRY_RUN"),
        **snapshot_human_only(text2),
    }
    if after["AUTO_TUNE_DRY_RUN"] != "true":
        raise Gate10JError("AUTO_TUNE_DRY_RUN must stay true (staging dry-run only)")
    if after["FEATURE_AUTO_TUNING"] != ("true" if enabled else "false"):
        raise Gate10JError("FEATURE_AUTO_TUNING did not land on expected value")
    for key in HUMAN_ONLY_KEYS:
        if after[key] != before[key]:
            raise Gate10JError(f"refusing to change human-only flag {key}")
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


def classify_audit_events(events: list[Any]) -> dict[str, list[dict[str, Any]]]:
    proposed: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for raw in events:
        if not isinstance(raw, dict):
            continue
        event = str(raw.get("event") or raw.get("type") or "")
        if event in PROPOSE_EVENTS:
            proposed.append(raw)
        elif event in APPLY_EVENTS:
            applied.append(raw)
        else:
            other.append(raw)
    return {"proposed": proposed, "applied": applied, "other": other}


def validate_staging_blueprint(repo: Path, python: str, blueprint: Path) -> None:
    assert_staging_blueprint(blueprint)
    cmd = [python, str(repo / "scripts" / "validate_render_blueprint.py"), str(blueprint)]
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        raise Gate10JError(f"{blueprint.name} validation failed")


def print_staging_sync_steps() -> None:
    log("ACTION_REQUIRED: Sync staging Blueprint (render.yaml) — not production")
    log("  1) Review FEATURE_AUTO_TUNING=true with AUTO_TUNE_DRY_RUN=true (staging only)")
    log("  2) Confirm FEATURE_NEURAL_BANDIT / FEATURE_RLHF_ROUTER / BANDIT_POLICY unchanged")
    log("  3) Render Dashboard → Blueprint saveiq → Manual Sync (not saveiq-production)")
    log("  4) make gate10j-auto-tune ARGS='--stage evaluate'")
    log("  5) After observe: make gate10j-auto-tune ARGS='--stage cleanup --confirm-autotune'")


class Gate10J:
    def __init__(
        self,
        *,
        repo: Path,
        staging_api: str,
        prod_api: str,
        staging_blueprint: Path,
        state_path: Path,
        dry_run: bool,
        python: str,
        report_dir: Path,
        skip_prod_10i: bool,
    ) -> None:
        self.repo = repo
        self.staging_api = staging_api.rstrip("/")
        self.prod_api = prod_api.rstrip("/")
        self.staging_bp = staging_blueprint
        self.state_path = state_path
        self.dry_run = dry_run
        self.python = python
        self.report_dir = report_dir
        self.skip_prod_10i = skip_prod_10i
        self.results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gate": "10J_auto_tune_staging_dry_run",
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

    def _writes_allowed(self, *, confirm: bool) -> bool:
        if self.dry_run:
            log("dry-run=True — no Blueprint/runtime writes")
            return False
        if not confirm:
            log("pass --confirm-autotune to write (default is dry-run / no write)")
            return False
        return True

    def check(self) -> bool:
        log("gate10j=check")
        ok = True
        text = self.staging_bp.read_text(encoding="utf-8")
        local_tune = blueprint_get(text, "FEATURE_AUTO_TUNING")
        local_dry = blueprint_get(text, "AUTO_TUNE_DRY_RUN")
        human = snapshot_human_only(text)
        ok &= self._note(
            "staging_blueprint_autotune_off",
            local_tune == "false",
            f"FEATURE_AUTO_TUNING={local_tune} (local render.yaml)",
        )
        ok &= self._note(
            "staging_blueprint_dry_run",
            local_dry == "true",
            f"AUTO_TUNE_DRY_RUN={local_dry}",
        )
        ok &= self._note(
            "human_only_untouched_local",
            human.get("FEATURE_NEURAL_BANDIT") == "false"
            and human.get("FEATURE_RLHF_ROUTER") == "false"
            and human.get("BANDIT_POLICY") == "linucb",
            f"human_only={json.dumps(human, sort_keys=True)}",
        )

        staging_token = require_staging_token()
        health = http_json(f"{self.staging_api}/health")
        ok &= self._note(
            "staging_reachable",
            bool(health),
            f"health_keys={sorted(health)[:8]}",
        )
        staging_safety = http_json(f"{self.staging_api}/admin/safety/status", token=staging_token)
        env = staging_safety.get("env") or {}
        runtime = staging_safety.get("runtime") or {}
        ok &= self._note(
            "staging_live_autotune_off",
            env.get("feature_auto_tuning") is not True,
            f"env_autotune={env.get('feature_auto_tuning')} "
            f"runtime_autotune={runtime.get('auto_tune_enabled')}",
        )

        if self.skip_prod_10i:
            ok &= self._note("prod_10i", True, "skipped (--skip-prod-10i)")
        else:
            prod_token = require_prod_token()
            kill = http_json(f"{self.prod_api}/admin/kill-switch/status", token=prod_token)
            ok &= self._note(
                "prod_10i_armed",
                kill.get("env_flag") is True
                and kill.get("armed") is True
                and kill.get("tripped") is not True,
                f"env_flag={kill.get('env_flag')} armed={kill.get('armed')} "
                f"tripped={kill.get('tripped')}",
            )
            prod_safety = http_json(f"{self.prod_api}/admin/safety/status", token=prod_token)
            prod_env = prod_safety.get("env") or {}
            ok &= self._note(
                "prod_autotune_off",
                prod_env.get("feature_auto_tuning") is not True,
                f"FEATURE_AUTO_TUNING={prod_env.get('feature_auto_tuning')} (must stay false)",
            )
        log(f"gate10j=check {'ok' if ok else 'error'}")
        return ok

    def staging_dry_run(self, *, confirm: bool) -> bool:
        log("gate10j=staging-dry-run")
        write = self._writes_allowed(confirm=confirm)
        result = apply_staging_autotune_blueprint(
            self.staging_bp,
            enabled=True,
            dry_run=not write,
        )
        if write:
            validate_staging_blueprint(self.repo, self.python, self.staging_bp)
        else:
            # Validate current on-disk file (still false) so operator sees a clean baseline.
            validate_staging_blueprint(self.repo, self.python, self.staging_bp)
        print_staging_sync_steps()
        if write:
            state = self.load_state()
            state["staging_blueprint"] = result["after"]
            state["staging_blueprint_at"] = datetime.now(timezone.utc).isoformat()
            self.save_state(state)
            log("staging-dry-run=ok FEATURE_AUTO_TUNING=true AUTO_TUNE_DRY_RUN=true (local yaml)")
        else:
            log("staging-dry-run=ok (dry-run; render.yaml not written)")
        return True

    def _hparams_from_status(self, safety: dict[str, Any]) -> dict[str, Any]:
        return dict(safety.get("hparams") or safety.get("runtime", {}).get("hparams") or {})

    def _arm_runtime_dry_run(self, token: str) -> dict[str, Any]:
        log("arming staging runtime overlay auto_tune_enabled=true dry_run=true canary=false")
        return http_json(
            f"{self.staging_api}/admin/safety/config",
            token=token,
            method="POST",
            body={
                "auto_tune_enabled": True,
                "dry_run": True,
                "auto_tune_canary_enabled": False,
                "manual_override": False,
            },
        )

    def _disarm_runtime_autotune(self, token: str) -> dict[str, Any]:
        return http_json(
            f"{self.staging_api}/admin/safety/config",
            token=token,
            method="POST",
            body={"auto_tune_enabled": False, "dry_run": True, "auto_tune_canary_enabled": False},
        )

    def evaluate(self, *, confirm: bool) -> bool:
        log("gate10j=evaluate (staging only)")
        token = require_staging_token()
        before = http_json(f"{self.staging_api}/admin/safety/status", token=token)
        env = before.get("env") or {}
        runtime = before.get("runtime") or {}
        hparams_before = self._hparams_from_status(before)
        if runtime.get("dry_run") is False and env.get("auto_tune_dry_run") is False:
            raise Gate10JError(
                "staging dry_run is false — refusing evaluate (would apply hparams). "
                "Set AUTO_TUNE_DRY_RUN=true / runtime dry_run=true first."
            )
        armed = bool(runtime.get("auto_tune_enabled")) or env.get("feature_auto_tuning") is True
        if not armed:
            if self._writes_allowed(confirm=confirm):
                self._arm_runtime_dry_run(token)
                before = http_json(f"{self.staging_api}/admin/safety/status", token=token)
                runtime = before.get("runtime") or {}
                hparams_before = self._hparams_from_status(before)
            else:
                log(
                    "WARN: staging auto-tune not armed; evaluate will skip unless you pass "
                    "--confirm-autotune (runtime overlay, dry_run=true) or Sync Blueprint"
                )

        if runtime.get("dry_run") is False:
            raise Gate10JError("runtime dry_run=false — abort (Gate 10J is propose-only)")

        started = time.time()
        result = http_json(
            f"{self.staging_api}/admin/safety/evaluate",
            token=token,
            method="POST",
            body={"force_tune": True},
        )
        tune = result.get("tune") or {}
        log(f"evaluate_tune={json.dumps(tune, sort_keys=True)[:800]}")
        applied = tune.get("applied") is True
        dry = tune.get("dry_run")
        skipped = tune.get("skipped") is True
        ok = True
        ok &= self._note(
            "propose_only",
            applied is not True,
            f"applied={tune.get('applied')} dry_run={dry} skipped={tune.get('skipped')} "
            f"reason={tune.get('reason')}",
        )
        if not skipped and dry is False:
            ok &= self._note("dry_run_flag", False, "evaluate returned dry_run=false")
        elif not skipped:
            ok &= self._note("dry_run_flag", dry is True, f"dry_run={dry}")

        after = http_json(f"{self.staging_api}/admin/safety/status", token=token)
        hparams_after = self._hparams_from_status(after)
        if hparams_before and hparams_after:
            ok &= self._note(
                "hparams_unchanged",
                hparams_before == hparams_after,
                f"before={hparams_before} after={hparams_after}",
            )

        audit = http_json(f"{self.staging_api}/admin/safety/audit?limit=20", token=token)
        events = audit.get("events") or []
        recent = []
        for raw in events if isinstance(events, list) else []:
            if not isinstance(raw, dict):
                continue
            ts = raw.get("ts")
            if isinstance(ts, int | float) and ts + 1.0 < started:
                continue
            recent.append(raw)
        classified = classify_audit_events(recent)
        log(
            "audit_proposed="
            f"{len(classified['proposed'])} audit_applied={len(classified['applied'])}"
        )
        if classified["proposed"]:
            sample = json.dumps(classified["proposed"][0], sort_keys=True)[:500]
            log(f"audit_propose_sample={sample}")
        apply_names = [e.get("event") for e in classified["applied"]]
        if classified["applied"]:
            ok &= self._note(
                "no_apply_audit",
                False,
                f"unexpected apply events this tick: {apply_names}",
            )
        else:
            ok &= self._note(
                "no_apply_audit",
                True,
                "no hparams_update/autotune_canary in this evaluate tick",
            )

        state = self.load_state()
        state["evaluate"] = {
            "tune": tune,
            "proposed_count": len(classified["proposed"]),
            "applied_count": len(classified["applied"]),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_state(state)
        self.results["evaluate"] = state["evaluate"]
        log(f"gate10j=evaluate {'ok' if ok else 'error'}")
        return ok

    def cleanup(self, *, confirm: bool) -> bool:
        log("gate10j=cleanup")
        write = self._writes_allowed(confirm=confirm)
        result = apply_staging_autotune_blueprint(
            self.staging_bp,
            enabled=False,
            dry_run=not write,
        )
        if write:
            validate_staging_blueprint(self.repo, self.python, self.staging_bp)
            token = require_staging_token()
            self._disarm_runtime_autotune(token)
            log("runtime auto_tune_enabled=false (staging overlay)")
            state = self.load_state()
            state["cleanup_blueprint"] = result["after"]
            state["cleaned_up_at"] = datetime.now(timezone.utc).isoformat()
            self.save_state(state)
            log("ACTION_REQUIRED: Sync staging Blueprint so FEATURE_AUTO_TUNING=false is durable")
            log("cleanup=ok FEATURE_AUTO_TUNING=false AUTO_TUNE_DRY_RUN=true")
        else:
            log("cleanup=ok (dry-run; render.yaml not written)")
        return True

    def write_report(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.report_dir / f"gate10j_auto_tune_{stamp}.json"
        save_json(path, self.results)
        save_json(self.report_dir / "gate10j_auto_tune_latest.json", self.results)
        log(f"report_written={path}")
        return path


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10J staging auto-tune dry-run scaffold")
    parser.add_argument("--stage", choices=STAGES, default="check")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force no writes even with --confirm-autotune",
    )
    parser.add_argument("--report", action="store_true")
    parser.add_argument(
        "--confirm-autotune",
        action="store_true",
        help="Allow staging Blueprint / runtime overlay writes (never production)",
    )
    parser.add_argument(
        "--skip-prod-10i",
        action="store_true",
        help="Skip live prod 10I armed check (offline / unit use only)",
    )
    parser.add_argument("--staging-api", default=os.environ.get("STAGING_API_URL", DEFAULT_STAGING))
    parser.add_argument("--prod-api", default=os.environ.get("API_URL", DEFAULT_PROD))
    parser.add_argument("--staging-blueprint", default=str(repo / "render.yaml"))
    parser.add_argument(
        "--state-file",
        default=str(repo / "artifacts" / "gate10j_auto_tune_state.json"),
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
    runner = Gate10J(
        repo=repo,
        staging_api=args.staging_api,
        prod_api=args.prod_api,
        staging_blueprint=Path(args.staging_blueprint),
        state_path=Path(args.state_file),
        dry_run=args.dry_run,
        python=python,
        report_dir=Path(args.report_dir),
        skip_prod_10i=args.skip_prod_10i,
    )
    log(f"gate10j=start stage={args.stage} dry_run={args.dry_run} confirm={args.confirm_autotune}")
    try:
        ok = False
        if args.stage == "check":
            ok = runner.check()
        elif args.stage == "staging-dry-run":
            ok = runner.staging_dry_run(confirm=args.confirm_autotune)
        elif args.stage == "evaluate":
            ok = runner.evaluate(confirm=args.confirm_autotune)
        elif args.stage == "cleanup":
            ok = runner.cleanup(confirm=args.confirm_autotune)
        if args.report:
            runner.results["ok"] = ok
            runner.write_report()
        log(f"gate10j={args.stage} {'ok' if ok else 'error'}")
        return 0 if ok else 1
    except Gate10JError as exc:
        log(f"gate10j=error {exc}")
        if args.report:
            runner.results["ok"] = False
            runner.results["error"] = str(exc)
            runner.write_report()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
