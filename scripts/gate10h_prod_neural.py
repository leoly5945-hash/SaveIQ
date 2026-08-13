#!/usr/bin/env python3
"""Gate 10H: production Neural Bandit enablement (human-only).

One flag at a time: FEATURE_NEURAL_BANDIT only (RLHF stays false).
Does **not** disable FEATURE_AI_ROUTER on rollback — surgical policy → linucb.

Phases (soak checkpoints, default ≥24h each):
  n10 → n25 → n50 → n100

By default phases are **operator soak / sign-off labels** stored in
artifacts/gate10h_prod_neural_state.json. They do **not** mutate live canary
percentage (post-10G live router is already at full exposure; shrinking canary
would regress Gate 10G). Pass --mutate-canary only with explicit intent.

Usage:
  export PROD_ADMIN_TOKEN=...

  .venv/bin/python scripts/gate10h_prod_neural.py --stage check
  .venv/bin/python scripts/gate10h_prod_neural.py --stage dry-run
  .venv/bin/python scripts/gate10h_prod_neural.py --stage apply --confirm-neural
  # → PR + Render Sync production, then:
  .venv/bin/python scripts/gate10h_prod_neural.py --stage verify --assume-synced
  .venv/bin/python scripts/gate10h_prod_neural.py --stage switch-neural --confirm-switch
  .venv/bin/python scripts/gate10h_prod_neural.py --stage start-soak --phase n10
  .venv/bin/python scripts/gate10h_prod_neural.py --stage advance --phase n25
  .venv/bin/python scripts/gate10h_prod_neural.py --stage status --report
  .venv/bin/python scripts/gate10h_prod_neural.py --stage rollback --confirm-rollback
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
USER_AGENT = "SaveIQ-Gate10H-ProdNeural/1.0"
DEFAULT_SOAK = 24 * 60 * 60
PHASES = ("n10", "n25", "n50", "n100")
PHASE_PCT = {"n10": 10, "n25": 25, "n50": 50, "n100": 100}


class Gate10HError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def http_json(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    expected: int | None = 200,
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
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if exc.code == 401:
            hint = " (set PROD_ADMIN_TOKEN from production ADMIN_API_TOKEN)"
        raise Gate10HError(
            f"{method} {url} -> HTTP {exc.code}: {err_body[:400]}{hint}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise Gate10HError(f"{method} {url} failed: {exc}") from exc
    if expected is not None and status != expected:
        raise Gate10HError(f"{method} {url} -> HTTP {status}: {payload[:400]}")
    parsed = json.loads(payload) if payload else {}
    if not isinstance(parsed, dict):
        raise Gate10HError(f"{url} did not return a JSON object")
    return parsed


def require_prod_token() -> str:
    token = os.environ.get("PROD_ADMIN_TOKEN", "").strip()
    if not token:
        raise Gate10HError(
            "PROD_ADMIN_TOKEN required (do not reuse staging ADMIN_API_TOKEN).\n"
            "  export PROD_ADMIN_TOKEN='...'  # Render → dealhunter-production-api"
        )
    return token


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m"


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


def apply_prod_blueprint(
    path: Path,
    *,
    neural_enabled: bool,
    dry_run: bool,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    before = {
        "FEATURE_NEURAL_BANDIT": blueprint_get(text, "FEATURE_NEURAL_BANDIT"),
        "FEATURE_RLHF_ROUTER": blueprint_get(text, "FEATURE_RLHF_ROUTER"),
        "BANDIT_POLICY": blueprint_get(text, "BANDIT_POLICY"),
        "FEATURE_KILL_SWITCH": blueprint_get(text, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text, "FEATURE_AUTO_TUNING"),
    }
    text2 = text
    text2 = blueprint_set(text2, "FEATURE_NEURAL_BANDIT", "true" if neural_enabled else "false")
    text2 = blueprint_set(text2, "FEATURE_RLHF_ROUTER", "false")
    text2 = blueprint_set(text2, "FEATURE_KILL_SWITCH", "false")
    text2 = blueprint_set(text2, "FEATURE_AUTO_TUNING", "false")
    # Keep Blueprint BANDIT_POLICY=linucb; runtime switch is separate.
    if blueprint_get(text2, "BANDIT_POLICY") not in {None, "linucb"}:
        text2 = blueprint_set(text2, "BANDIT_POLICY", "linucb")

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


def validate_prod_blueprint(repo: Path, python: str, *, allow_neural: bool) -> None:
    cmd = [
        python,
        str(repo / "scripts" / "validate_render_blueprint.py"),
        "render-production.yaml",
        "--profile",
        "production",
        "--allow-live-ai",
    ]
    if allow_neural:
        cmd.append("--allow-neural-bandit")
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        raise Gate10HError("production Blueprint validation failed")


class ProdNeuralRollout:
    def __init__(
        self,
        *,
        repo: Path,
        api_url: str,
        blueprint_path: Path,
        state_path: Path,
        report_dir: Path,
        dry_run: bool,
        soak_seconds: int,
        mutate_canary: bool,
        python: str,
    ) -> None:
        self.repo = repo
        self.api_url = api_url.rstrip("/")
        self.blueprint_path = blueprint_path
        self.state_path = state_path
        self.report_dir = report_dir
        self.dry_run = dry_run
        self.soak_seconds = soak_seconds
        self.mutate_canary = mutate_canary
        self.python = python
        self.results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gate": "10H_prod_neural",
            "dry_run": dry_run,
            "checks": [],
            "actions": [],
        }

    def _note(self, name: str, ok: bool, message: str) -> bool:
        status = "PASS" if ok else "FAIL"
        log(f"  {name}: {status} — {message}")
        self.results["checks"].append({"step": name, "status": status, "message": message})
        return ok

    def load_state(self) -> dict[str, Any]:
        state = load_json(self.state_path)
        state.setdefault("phases", {})
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(self.state_path, state)
        log(f"state_written={self.state_path}")

    def check(self) -> bool:
        log("gate10h_prod_neural=check")
        ok = True
        token = require_prod_token()
        try:
            health = http_json(f"{self.api_url}/health")
            ok &= self._note("health", health.get("status") == "ok", str(health.get("status")))
        except Gate10HError as exc:
            ok &= self._note("health", False, str(exc))

        try:
            router = http_json(f"{self.api_url}/admin/router-status", token=token)
            ok &= self._note(
                "router_live",
                router.get("active") is True and str(router.get("mode") or "").lower() == "live",
                f"active={router.get('active')} mode={router.get('mode')}",
            )
        except Gate10HError as exc:
            ok &= self._note("router_live", False, str(exc))

        try:
            safety = http_json(f"{self.api_url}/admin/safety/status", token=token)
            env = safety.get("env") or {}
            runtime = safety.get("runtime") or {}
            ok &= self._note(
                "safety_off",
                env.get("feature_kill_switch") is not True
                and env.get("feature_auto_tuning") is not True
                and runtime.get("tripped") is not True,
                f"kill={env.get('feature_kill_switch')} "
                f"autotune={env.get('feature_auto_tuning')} "
                f"tripped={runtime.get('tripped')}",
            )
        except Gate10HError as exc:
            ok &= self._note("safety_off", False, str(exc))

        try:
            bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
            flags = bandit.get("flags") or {}
            neural = bandit.get("neural") or {}
            ok &= self._note(
                "bandit_snapshot",
                True,
                f"policy={bandit.get('policy')} flags.neural={flags.get('neural')} "
                f"flags.rlhf={flags.get('rlhf')} neural.ready={neural.get('ready')} "
                f"samples={neural.get('sample_count')}",
            )
            if flags.get("rlhf") is True:
                ok &= self._note(
                    "rlhf_off",
                    False,
                    "FEATURE_RLHF_ROUTER is on — disable before prod neural (one flag at a time)",
                )
        except Gate10HError as exc:
            ok &= self._note("bandit_snapshot", False, str(exc))

        # Local prereq report hint
        prereq = self.report_dir / "gate10h_prod_prereq_report.json"
        if prereq.is_file():
            data = load_json(prereq)
            ok &= self._note(
                "prod_prereq_report",
                bool(data.get("passed")),
                f"passed={data.get('passed')} checked_at={data.get('checked_at')}",
            )
        else:
            ok &= self._note(
                "prod_prereq_report",
                False,
                "missing artifacts/gate10h_prod_prereq_report.json — run gate10h_check_prod_prereq.py",
            )

        log(f"gate10h_prod_neural=check {'ok' if ok else 'error'}")
        return ok

    def dry_run_blueprint(self) -> bool:
        log("gate10h_prod_neural=dry-run")
        apply_prod_blueprint(self.blueprint_path, neural_enabled=True, dry_run=True)
        validate_prod_blueprint(self.repo, self.python, allow_neural=True)
        self.results["actions"].append({"step": "dry_run", "status": "PASS"})
        return True

    def apply_blueprint(self, *, confirm: bool) -> bool:
        log("gate10h_prod_neural=apply")
        if not confirm:
            raise Gate10HError("refusing apply without --confirm-neural")
        if self.dry_run:
            return self.dry_run_blueprint()
        result = apply_prod_blueprint(self.blueprint_path, neural_enabled=True, dry_run=False)
        validate_prod_blueprint(self.repo, self.python, allow_neural=True)
        state = self.load_state()
        state["blueprint_applied_at"] = datetime.now(timezone.utc).isoformat()
        state["blueprint_after"] = result["after"]
        self.save_state(state)
        self.results["actions"].append({"step": "apply", "status": "PASS", "after": result["after"]})
        log("ACTION_REQUIRED:")
        log("  1) Commit/PR render-production.yaml (FEATURE_NEURAL_BANDIT=true)")
        log("  2) Render Sync **production** Blueprint")
        log("  3) make gate10h-prod-neural ARGS='--stage verify --assume-synced'")
        return True

    def verify(self, *, assume_synced: bool) -> bool:
        log("gate10h_prod_neural=verify")
        token = require_prod_token()
        bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
        flags = bandit.get("flags") or {}
        neural = bandit.get("neural") or {}
        ok = flags.get("neural") is True
        if not ok and not assume_synced:
            raise Gate10HError(
                "flags.neural is not true — Sync production Blueprint after --stage apply"
            )
        if not ok and assume_synced:
            raise Gate10HError("flags.neural still false after --assume-synced; Sync incomplete?")
        # ready may stay false with low samples — flag on is the Sync gate.
        log(
            f"verify=ok policy={bandit.get('policy')} flags.neural={flags.get('neural')} "
            f"neural.ready={neural.get('ready')} samples={neural.get('sample_count')}"
        )
        if neural.get("ready") is not True:
            log(
                "NOTE: neural.ready=false (expected with low samples). "
                "Train/logs may raise readiness; policy switch still allowed with LinUCB fallback."
            )
        state = self.load_state()
        state["verified_at"] = datetime.now(timezone.utc).isoformat()
        state["bandit"] = {
            "policy": bandit.get("policy"),
            "flags": flags,
            "neural": neural,
        }
        self.save_state(state)
        self.results["actions"].append(
            {
                "step": "verify",
                "status": "PASS",
                "neural_ready": neural.get("ready"),
                "sample_count": neural.get("sample_count"),
            }
        )
        return True

    def switch_neural(self, *, confirm: bool) -> bool:
        log("gate10h_prod_neural=switch-neural")
        if not confirm:
            raise Gate10HError("refusing switch without --confirm-switch")
        token = require_prod_token()
        if self.dry_run:
            log("[DRY RUN] would POST /admin/bandit/switch_policy policy=neural")
            return True
        bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
        if (bandit.get("flags") or {}).get("neural") is not True:
            raise Gate10HError("flags.neural must be true before switch")
        switched = http_json(
            f"{self.api_url}/admin/bandit/switch_policy",
            token=token,
            method="POST",
            body={"policy": "neural"},
        )
        log(f"switch_policy={json.dumps(switched, sort_keys=True)}")
        state = self.load_state()
        state["policy_switched_at"] = datetime.now(timezone.utc).isoformat()
        state["policy"] = "neural"
        self.save_state(state)
        self.results["actions"].append({"step": "switch_neural", "status": "PASS", "body": switched})
        return True

    def start_soak(self, phase: str) -> bool:
        if phase not in PHASES:
            raise Gate10HError(f"phase must be one of {PHASES}")
        state = self.load_state()
        now = time.time()
        phases = state.setdefault("phases", {})
        if phase in phases and phases[phase].get("started_at"):
            log(f"soak already started for {phase} at {phases[phase].get('started_at')}")
            return True
        # Enforce order
        idx = PHASES.index(phase)
        if idx > 0:
            prev = PHASES[idx - 1]
            prev_meta = phases.get(prev) or {}
            started = float(prev_meta.get("started_at_epoch") or 0)
            if started <= 0:
                raise Gate10HError(f"start previous phase {prev} before {phase}")
            elapsed = now - started
            if elapsed < self.soak_seconds and not prev_meta.get("completed"):
                raise Gate10HError(
                    f"soak for {prev} incomplete "
                    f"({fmt_duration(elapsed)} < {fmt_duration(self.soak_seconds)}); "
                    f"use --stage advance --phase {phase} after soak"
                )
        phases[phase] = {
            "target_pct": PHASE_PCT[phase],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "started_at_epoch": now,
            "completed": False,
            "mutate_canary": self.mutate_canary,
        }
        if self.mutate_canary:
            self._set_canary(PHASE_PCT[phase])
        else:
            log(
                f"soak_checkpoint={phase} target_label={PHASE_PCT[phase]}% "
                "(canary not mutated; monitoring sign-off only)"
            )
        state["current_phase"] = phase
        self.save_state(state)
        self.results["actions"].append({"step": "start_soak", "phase": phase, "status": "PASS"})
        return True

    def advance(self, phase: str) -> bool:
        """Mark previous soak complete and start the next phase."""
        if phase not in PHASES:
            raise Gate10HError(f"phase must be one of {PHASES}")
        idx = PHASES.index(phase)
        if idx == 0:
            return self.start_soak(phase)
        prev = PHASES[idx - 1]
        state = self.load_state()
        phases = state.setdefault("phases", {})
        prev_meta = phases.get(prev) or {}
        started = float(prev_meta.get("started_at_epoch") or 0)
        if started <= 0:
            raise Gate10HError(f"previous phase {prev} never started")
        elapsed = time.time() - started
        if elapsed < self.soak_seconds:
            raise Gate10HError(
                f"cannot advance to {phase}: {prev} soak "
                f"{fmt_duration(elapsed)} < {fmt_duration(self.soak_seconds)}"
            )
        prev_meta["completed"] = True
        prev_meta["completed_at"] = datetime.now(timezone.utc).isoformat()
        prev_meta["soak_seconds"] = elapsed
        phases[prev] = prev_meta
        self.save_state(state)
        log(f"phase_complete={prev} soak={fmt_duration(elapsed)}")
        return self.start_soak(phase)

    def _set_canary(self, percentage: int) -> None:
        token = require_prod_token()
        if self.dry_run:
            log(f"[DRY RUN] would set canary enabled percentage={percentage}")
            return
        body = {"enabled": True, "percentage": int(percentage)}
        result = http_json(
            f"{self.api_url}/admin/canary/config",
            token=token,
            method="POST",
            body=body,
        )
        log(
            f"canary_mutated enabled={result.get('enabled')} "
            f"percentage={result.get('percentage')}"
        )

    def status(self) -> bool:
        log("gate10h_prod_neural=status")
        token = require_prod_token()
        state = self.load_state()
        bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
        canary = http_json(f"{self.api_url}/admin/canary/status", token=token)
        current = state.get("current_phase")
        phases = state.get("phases") or {}
        log(f"policy={bandit.get('policy')} flags={bandit.get('flags')}")
        log(f"neural={bandit.get('neural')}")
        log(f"canary enabled={canary.get('enabled')} percentage={canary.get('percentage')}")
        log(f"current_phase={current}")
        now = time.time()
        for name in PHASES:
            meta = phases.get(name) or {}
            started = float(meta.get("started_at_epoch") or 0)
            if not started:
                log(f"  {name}: not_started")
                continue
            elapsed = now - started
            left = max(0.0, self.soak_seconds - elapsed)
            log(
                f"  {name}: started={meta.get('started_at')} "
                f"elapsed={fmt_duration(elapsed)} remaining={fmt_duration(left)} "
                f"completed={meta.get('completed')}"
            )
        self.results["status"] = {
            "bandit": {
                "policy": bandit.get("policy"),
                "flags": bandit.get("flags"),
                "neural": bandit.get("neural"),
            },
            "canary": {
                "enabled": canary.get("enabled"),
                "percentage": canary.get("percentage"),
            },
            "state": state,
        }
        return True

    def rollback(self, *, confirm: bool, disable_flag: bool) -> bool:
        log("gate10h_prod_neural=rollback")
        if not confirm:
            raise Gate10HError("refusing rollback without --confirm-rollback")
        token = require_prod_token()
        if self.dry_run:
            log("[DRY RUN] would switch policy=linucb (+ optional blueprint false)")
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
        actions: list[dict[str, Any]] = [
            {"step": "switch_linucb", "status": "PASS", "body": restored}
        ]
        if disable_flag:
            result = apply_prod_blueprint(
                self.blueprint_path, neural_enabled=False, dry_run=False
            )
            validate_prod_blueprint(self.repo, self.python, allow_neural=False)
            state["blueprint_after_rollback"] = result["after"]
            actions.append({"step": "blueprint_false", "status": "PASS", "after": result["after"]})
            log("ACTION_REQUIRED: Sync production Blueprint to clear FEATURE_NEURAL_BANDIT")
        self.save_state(state)
        self.results["actions"].extend(actions)
        log("rollback=ok (FEATURE_AI_ROUTER left unchanged)")
        return True

    def write_report(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.report_dir / f"gate10h_prod_neural_{stamp}.json"
        save_json(path, self.results)
        save_json(self.report_dir / "gate10h_prod_neural_latest.json", self.results)
        log(f"report_written={path}")
        return path


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10H production Neural enablement")
    parser.add_argument(
        "--stage",
        choices=[
            "check",
            "dry-run",
            "apply",
            "verify",
            "switch-neural",
            "start-soak",
            "advance",
            "status",
            "rollback",
        ],
        default="check",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--confirm-neural", action="store_true")
    parser.add_argument("--confirm-switch", action="store_true")
    parser.add_argument("--confirm-rollback", action="store_true")
    parser.add_argument(
        "--disable-flag",
        action="store_true",
        help="With rollback: also set FEATURE_NEURAL_BANDIT=false in Blueprint",
    )
    parser.add_argument("--assume-synced", action="store_true")
    parser.add_argument(
        "--phase",
        choices=PHASES,
        default="",
        help="Soak phase for start-soak / advance",
    )
    parser.add_argument(
        "--mutate-canary",
        action="store_true",
        help="Also set /admin/canary percentage to phase target (off by default)",
    )
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_PROD))
    parser.add_argument(
        "--blueprint",
        default=str(repo / "render-production.yaml"),
    )
    parser.add_argument(
        "--state-file",
        default=str(repo / "artifacts" / "gate10h_prod_neural_state.json"),
    )
    parser.add_argument("--report-dir", default=str(repo / "artifacts"))
    parser.add_argument(
        "--soak-seconds",
        type=int,
        default=int(os.environ.get("GATE10H_SOAK_SECONDS", str(DEFAULT_SOAK))),
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

    rollout = ProdNeuralRollout(
        repo=repo,
        api_url=args.api_url,
        blueprint_path=Path(args.blueprint),
        state_path=Path(args.state_file),
        report_dir=Path(args.report_dir),
        dry_run=args.dry_run,
        soak_seconds=args.soak_seconds,
        mutate_canary=args.mutate_canary,
        python=python,
    )

    log(f"gate10h_prod_neural=start stage={args.stage} dry_run={args.dry_run}")
    try:
        ok = False
        if args.stage == "check":
            ok = rollout.check()
        elif args.stage == "dry-run":
            ok = rollout.dry_run_blueprint()
        elif args.stage == "apply":
            ok = rollout.apply_blueprint(confirm=args.confirm_neural)
        elif args.stage == "verify":
            ok = rollout.verify(assume_synced=args.assume_synced)
        elif args.stage == "switch-neural":
            ok = rollout.switch_neural(confirm=args.confirm_switch)
        elif args.stage == "start-soak":
            if not args.phase:
                raise Gate10HError("--phase required for start-soak")
            ok = rollout.start_soak(args.phase)
        elif args.stage == "advance":
            if not args.phase:
                raise Gate10HError("--phase required for advance")
            ok = rollout.advance(args.phase)
        elif args.stage == "status":
            ok = rollout.status()
        elif args.stage == "rollback":
            ok = rollout.rollback(
                confirm=args.confirm_rollback,
                disable_flag=args.disable_flag,
            )
        else:
            raise Gate10HError(f"unknown stage {args.stage}")

        if args.report:
            rollout.write_report()
        return 0 if ok else 1
    except Gate10HError as exc:
        log(f"gate10h_prod_neural=error: {exc}")
        if args.report:
            rollout.results["error"] = str(exc)
            rollout.write_report()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
