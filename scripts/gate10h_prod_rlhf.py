#!/usr/bin/env python3
"""Gate 10H: production RLHF enablement AFTER neural n100 soak PASS.

One extra flag: FEATURE_RLHF_ROUTER=true (neural may stay true).
Rollback is surgical: policy → linucb. Never disables FEATURE_AI_ROUTER.

There is no Render Sync API in-repo — ``--stage sync`` prints operator steps.

Usage:
  export PROD_ADMIN_TOKEN=...

  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage check
  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage blueprint --dry-run
  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage blueprint --confirm-rlhf
  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage sync
  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage verify --assume-synced
  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage canary --traffic 10 --confirm-switch
  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage promote --confirm-promote
  .venv/bin/python scripts/gate10h_prod_rlhf.py --stage rollback --confirm-rollback
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

DEFAULT_PROD = "https://dealhunter-production-api.onrender.com"
USER_AGENT = "SaveIQ-Gate10H-ProdRlhf/1.0"
DEFAULT_SOAK = 24 * 60 * 60
NEURAL_STATE = "artifacts/gate10h_prod_neural_state.json"


class Gate10HError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def require_prod_token() -> str:
    token = os.environ.get("PROD_ADMIN_TOKEN", "").strip()
    if not token:
        raise Gate10HError("PROD_ADMIN_TOKEN required (production ADMIN_API_TOKEN)")
    return token


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def http_json(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["X-Admin-Token"] = token
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
        hint = " (PROD_ADMIN_TOKEN)" if exc.code == 401 else ""
        raise Gate10HError(f"{method} {url} -> HTTP {exc.code}: {err[:400]}{hint}") from exc
    parsed = json.loads(payload) if payload else {}
    if not isinstance(parsed, dict):
        raise Gate10HError(f"{url} did not return a JSON object")
    return parsed


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
        raise Gate10HError(f"failed to set {key} in Blueprint (matches={n})")
    return new_text


def apply_prod_blueprint(path: Path, *, rlhf_enabled: bool, dry_run: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    before = {
        "FEATURE_NEURAL_BANDIT": blueprint_get(text, "FEATURE_NEURAL_BANDIT"),
        "FEATURE_RLHF_ROUTER": blueprint_get(text, "FEATURE_RLHF_ROUTER"),
        "BANDIT_POLICY": blueprint_get(text, "BANDIT_POLICY"),
        "FEATURE_KILL_SWITCH": blueprint_get(text, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text, "FEATURE_AUTO_TUNING"),
    }
    text2 = text
    text2 = blueprint_set(text2, "FEATURE_RLHF_ROUTER", "true" if rlhf_enabled else "false")
    text2 = blueprint_set(text2, "FEATURE_KILL_SWITCH", "false")
    text2 = blueprint_set(text2, "FEATURE_AUTO_TUNING", "false")
    # Keep neural as currently set (expected true after n100).
    after = {
        "FEATURE_NEURAL_BANDIT": blueprint_get(text2, "FEATURE_NEURAL_BANDIT"),
        "FEATURE_RLHF_ROUTER": blueprint_get(text2, "FEATURE_RLHF_ROUTER"),
        "BANDIT_POLICY": blueprint_get(text2, "BANDIT_POLICY"),
        "FEATURE_KILL_SWITCH": blueprint_get(text2, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text2, "FEATURE_AUTO_TUNING"),
    }
    if dry_run:
        log(f"blueprint_dry_run before={json.dumps(before, sort_keys=True)}")
        log(f"blueprint_dry_run after={json.dumps(after, sort_keys=True)}")
        log("blueprint_dry_run=ok (no write)")
    else:
        path.write_text(text2, encoding="utf-8")
        log(f"blueprint_updated={path}")
        log(f"blueprint_after={json.dumps(after, sort_keys=True)}")
    return {"before": before, "after": after, "changed": text2 != text, "dry_run": dry_run}


def validate_prod_blueprint(repo: Path, python: str, *, rlhf_on: bool, neural_on: bool) -> None:
    cmd = [
        python,
        str(repo / "scripts" / "validate_render_blueprint.py"),
        "render-production.yaml",
        "--profile",
        "production",
        "--allow-live-ai",
    ]
    if neural_on:
        cmd.append("--allow-neural-bandit")
    if rlhf_on:
        cmd.append("--allow-rlhf-router")
    if neural_on and rlhf_on:
        cmd.append("--allow-rlhf-after-neural")
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        raise Gate10HError("production Blueprint validation failed")


class ProdRlhf:
    def __init__(
        self,
        *,
        repo: Path,
        api_url: str,
        blueprint: Path,
        state_path: Path,
        neural_state: Path,
        dry_run: bool,
        soak_seconds: float,
        mutate_canary: bool,
        python: str,
        report_dir: Path,
    ) -> None:
        self.repo = repo
        self.api_url = api_url.rstrip("/")
        self.blueprint = blueprint
        self.state_path = state_path
        self.neural_state = neural_state
        self.dry_run = dry_run
        self.soak_seconds = soak_seconds
        self.mutate_canary = mutate_canary
        self.python = python
        self.report_dir = report_dir
        self.results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gate": "10H_prod_rlhf",
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
        log("gate10h_prod_rlhf=check")
        ok = True
        token = require_prod_token()
        neural = load_json(self.neural_state)
        n100 = (neural.get("phases") or {}).get("n100") or {}
        started = float(n100.get("started_at_epoch") or 0)
        completed = bool(n100.get("completed"))
        elapsed = (time.time() - started) if started else 0.0
        n100_ok = completed or (started > 0 and elapsed >= self.soak_seconds)
        ok &= self._note(
            "neural_n100",
            n100_ok,
            f"completed={completed} started={n100.get('started_at')} "
            f"current_phase={neural.get('current_phase')}",
        )
        monitor = self.repo / "artifacts" / "gate10h_soak_report_n100_latest.json"
        if monitor.is_file():
            report = load_json(monitor)
            ok &= self._note(
                "n100_monitor",
                str(report.get("status") or "").upper() == "PASS",
                f"status={report.get('status')} checked_at={report.get('checked_at')}",
            )
        else:
            ok &= self._note("n100_monitor", False, f"missing {monitor}")

        bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
        flags = bandit.get("flags") or {}
        ok &= self._note(
            "neural_flag",
            flags.get("neural") is True,
            f"flags={flags} policy={bandit.get('policy')}",
        )
        safety = http_json(f"{self.api_url}/admin/safety/status", token=token)
        env = safety.get("env") or {}
        ok &= self._note(
            "safety_off",
            env.get("feature_kill_switch") is not True
            and env.get("feature_auto_tuning") is not True,
            f"kill={env.get('feature_kill_switch')} autotune={env.get('feature_auto_tuning')}",
        )
        log(f"gate10h_prod_rlhf=check {'ok' if ok else 'error'}")
        return ok

    def blueprint_stage(self, *, confirm: bool) -> bool:
        log("gate10h_prod_rlhf=blueprint")
        dry = self.dry_run or not confirm
        if not confirm and not self.dry_run:
            log("pass --confirm-rlhf to write render-production.yaml (or --dry-run)")
            dry = True
        result = apply_prod_blueprint(self.blueprint, rlhf_enabled=True, dry_run=dry)
        neural_on = (result["after"].get("FEATURE_NEURAL_BANDIT") or "true") == "true"
        validate_prod_blueprint(
            self.repo, self.python, rlhf_on=True, neural_on=neural_on
        )
        if not dry:
            state = self.load_state()
            state["blueprint_applied_at"] = datetime.now(timezone.utc).isoformat()
            state["blueprint_after"] = result["after"]
            self.save_state(state)
            log("ACTION_REQUIRED: commit/PR render-production.yaml then Render Sync production")
        return True

    def sync_hint(self) -> bool:
        log("gate10h_prod_rlhf=sync")
        log("There is no in-repo Render Sync API.")
        log("  1) Merge PR that sets FEATURE_RLHF_ROUTER=true")
        log("  2) Render → production Blueprint → Sync")
        log("  3) Wait for API deploy")
        log("  4) make gate10h-prod-rlhf ARGS='--stage verify --assume-synced'")
        self.results["sync"] = "operator_required"
        return True

    def verify(self, *, assume_synced: bool) -> bool:
        log("gate10h_prod_rlhf=verify")
        token = require_prod_token()
        bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
        flags = bandit.get("flags") or {}
        rlhf = bandit.get("rlhf") or {}
        ok = flags.get("rlhf") is True
        if not ok:
            msg = "flags.rlhf is not true"
            if assume_synced:
                raise Gate10HError(msg + " after --assume-synced; Sync incomplete?")
            raise Gate10HError(msg + " — Sync production Blueprint first")
        log(
            f"verify=ok policy={bandit.get('policy')} flags.rlhf={flags.get('rlhf')} "
            f"rlhf.ready={rlhf.get('ready')} samples={rlhf.get('sample_count')}"
        )
        if rlhf.get("ready") is not True:
            log("NOTE: rlhf.ready=false expected with low samples; LinUCB fallback applies")
        state = self.load_state()
        state["verified_at"] = datetime.now(timezone.utc).isoformat()
        state["bandit"] = {"policy": bandit.get("policy"), "flags": flags, "rlhf": rlhf}
        self.save_state(state)
        return True

    def canary(self, *, traffic: int, confirm: bool) -> bool:
        log(f"gate10h_prod_rlhf=canary traffic={traffic}")
        if not confirm:
            raise Gate10HError("refusing canary switch without --confirm-switch")
        token = require_prod_token()
        if self.dry_run:
            log(f"[DRY RUN] would switch policy=rlhf (canary_mutate={self.mutate_canary} pct={traffic})")
            return True
        bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
        if (bandit.get("flags") or {}).get("rlhf") is not True:
            raise Gate10HError("flags.rlhf must be true before switch")
        switched = http_json(
            f"{self.api_url}/admin/bandit/switch_policy",
            token=token,
            method="POST",
            body={"policy": "rlhf"},
        )
        log(f"switch_policy={json.dumps(switched, sort_keys=True)}")
        if self.mutate_canary:
            http_json(
                f"{self.api_url}/admin/canary/config",
                token=token,
                method="POST",
                body={"enabled": True, "percentage": int(traffic)},
            )
            log(f"canary_mutated percentage={traffic}")
        else:
            log(
                f"rlhf_canary_label={traffic}% (canary not mutated; "
                "policy=rlhf with LinUCB fallback if not ready)"
            )
        state = self.load_state()
        state["canary_started_at"] = datetime.now(timezone.utc).isoformat()
        state["canary_traffic_label"] = traffic
        state["policy"] = "rlhf"
        self.save_state(state)
        log("Start: make gate10h-monitor-soak ARGS='--phase n100 --once' still valid for HTTP SLIs")
        return True

    def promote(self, *, confirm: bool) -> bool:
        log("gate10h_prod_rlhf=promote")
        if not confirm:
            raise Gate10HError("refusing promote without --confirm-promote")
        token = require_prod_token()
        state = self.load_state()
        started = state.get("canary_started_at")
        if started:
            # ISO parse best-effort
            try:
                started_ts = datetime.fromisoformat(str(started).replace("Z", "+00:00")).timestamp()
                elapsed = time.time() - started_ts
                if elapsed < self.soak_seconds:
                    raise Gate10HError(
                        f"canary soak incomplete ({elapsed:.0f}s < {self.soak_seconds:.0f}s)"
                    )
            except Gate10HError:
                raise
            except Exception:  # noqa: BLE001
                log("WARN: could not parse canary_started_at; continuing with confirm")
        if self.dry_run:
            log("[DRY RUN] would keep policy=rlhf (100% label)")
            return True
        switched = http_json(
            f"{self.api_url}/admin/bandit/switch_policy",
            token=token,
            method="POST",
            body={"policy": "rlhf"},
        )
        log(f"switch_policy={json.dumps(switched, sort_keys=True)}")
        if self.mutate_canary:
            http_json(
                f"{self.api_url}/admin/canary/config",
                token=token,
                method="POST",
                body={"enabled": True, "percentage": 100},
            )
        state["promoted_at"] = datetime.now(timezone.utc).isoformat()
        state["policy"] = "rlhf"
        self.save_state(state)
        log("gate10h_prod_rlhf=promote ok")
        return True

    def rollback(self, *, confirm: bool, disable_flag: bool) -> bool:
        log("gate10h_prod_rlhf=rollback")
        if not confirm:
            raise Gate10HError("refusing rollback without --confirm-rollback")
        token = require_prod_token()
        if self.dry_run:
            log("[DRY RUN] would switch policy=linucb (AI router unchanged)")
            return True
        restored = http_json(
            f"{self.api_url}/admin/bandit/switch_policy",
            token=token,
            method="POST",
            body={"policy": "linucb"},
        )
        log(f"switch_policy={json.dumps(restored, sort_keys=True)}")
        state = self.load_state()
        state["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
        state["policy"] = "linucb"
        if disable_flag:
            result = apply_prod_blueprint(self.blueprint, rlhf_enabled=False, dry_run=False)
            neural_on = (result["after"].get("FEATURE_NEURAL_BANDIT") or "false") == "true"
            validate_prod_blueprint(
                self.repo, self.python, rlhf_on=False, neural_on=neural_on
            )
            state["blueprint_after_rollback"] = result["after"]
            log("ACTION_REQUIRED: Sync production to clear FEATURE_RLHF_ROUTER")
        self.save_state(state)
        log("rollback=ok (FEATURE_AI_ROUTER left unchanged)")
        return True

    def write_report(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.report_dir / f"gate10h_prod_rlhf_{stamp}.json"
        save_json(path, self.results)
        save_json(self.report_dir / "gate10h_prod_rlhf_latest.json", self.results)
        log(f"report_written={path}")
        return path


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10H production RLHF after neural n100")
    parser.add_argument(
        "--stage",
        choices=["check", "blueprint", "sync", "verify", "canary", "promote", "rollback"],
        default="check",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--confirm-rlhf", action="store_true")
    parser.add_argument("--confirm-switch", action="store_true")
    parser.add_argument("--confirm-promote", action="store_true")
    parser.add_argument("--confirm-rollback", action="store_true")
    parser.add_argument("--assume-synced", action="store_true")
    parser.add_argument("--disable-flag", action="store_true")
    parser.add_argument("--traffic", type=int, default=10, help="Canary label % (default 10)")
    parser.add_argument("--mutate-canary", action="store_true")
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_PROD))
    parser.add_argument("--blueprint", default=str(repo / "render-production.yaml"))
    parser.add_argument(
        "--state-file",
        default=str(repo / "artifacts" / "gate10h_prod_rlhf_state.json"),
    )
    parser.add_argument("--neural-state", default=str(repo / NEURAL_STATE))
    parser.add_argument("--report-dir", default=str(repo / "artifacts"))
    parser.add_argument(
        "--soak-seconds",
        type=float,
        default=float(os.environ.get("GATE10H_SOAK_SECONDS", str(DEFAULT_SOAK))),
    )
    parser.add_argument("--python", default="")
    parser.add_argument("--repo-root", default=str(repo))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root)
    python = args.python or os.environ.get("PYTHON") or str(repo / ".venv" / "bin" / "python")
    if not Path(python).exists():
        python = sys.executable
    runner = ProdRlhf(
        repo=repo,
        api_url=args.api_url,
        blueprint=Path(args.blueprint),
        state_path=Path(args.state_file),
        neural_state=Path(args.neural_state),
        dry_run=args.dry_run,
        soak_seconds=args.soak_seconds,
        mutate_canary=args.mutate_canary,
        python=python,
        report_dir=Path(args.report_dir),
    )
    log(f"gate10h_prod_rlhf=start stage={args.stage} dry_run={args.dry_run}")
    try:
        ok = False
        if args.stage == "check":
            ok = runner.check()
        elif args.stage == "blueprint":
            ok = runner.blueprint_stage(confirm=args.confirm_rlhf)
        elif args.stage == "sync":
            ok = runner.sync_hint()
        elif args.stage == "verify":
            ok = runner.verify(assume_synced=args.assume_synced)
        elif args.stage == "canary":
            ok = runner.canary(traffic=args.traffic, confirm=args.confirm_switch)
        elif args.stage == "promote":
            ok = runner.promote(confirm=args.confirm_promote)
        elif args.stage == "rollback":
            ok = runner.rollback(confirm=args.confirm_rollback, disable_flag=args.disable_flag)
        if args.report:
            runner.write_report()
        return 0 if ok else 1
    except Gate10HError as exc:
        log(f"gate10h_prod_rlhf=error: {exc}")
        if args.report:
            runner.results["error"] = str(exc)
            runner.write_report()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
