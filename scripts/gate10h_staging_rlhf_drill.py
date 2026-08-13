#!/usr/bin/env python3
"""Gate 10H: staging RLHF Router evaluation drill.

Mirrors scripts/gate10h_staging_neural.py for FEATURE_RLHF_ROUTER (one flag at a time).

- Staging Blueprint: render.yaml (FEATURE_RLHF_ROUTER=true; neural stays false)
- Admin: /admin/bandit/status, /admin/bandit/switch_policy {"policy":"rlhf"}
- Benchmark: POST /admin/benchmark/run vs linucb
- Cleanup: policy=linucb + FEATURE_RLHF_ROUTER=false (never disables FEATURE_AI_ROUTER)

Usage:
  export STAGING_ADMIN_TOKEN=...
  export PROD_ADMIN_TOKEN=...   # optional Gate 10G prereq

  .venv/bin/python scripts/gate10h_staging_rlhf_drill.py --stage check
  .venv/bin/python scripts/gate10h_staging_rlhf_drill.py --stage setup --dry-run
  .venv/bin/python scripts/gate10h_staging_rlhf_drill.py --stage setup
  # → commit/PR or Sync staging Blueprint, then:
  .venv/bin/python scripts/gate10h_staging_rlhf_drill.py --stage evaluate --assume-synced --report
  .venv/bin/python scripts/gate10h_staging_rlhf_drill.py --stage cleanup
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
USER_AGENT = "SaveIQ-Gate10H-StagingRlhf/1.0"
DEFAULT_SOAK = 24 * 60 * 60


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
            host_hint = "STAGING_ADMIN_TOKEN" if "staging" in url else "PROD_ADMIN_TOKEN"
            hint = (
                f" (wrong/missing admin token — set {host_hint} from matching "
                "Render Environment ADMIN_API_TOKEN)"
            )
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


def require_staging_token() -> str:
    token = (
        os.environ.get("STAGING_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
    )
    if not token:
        raise Gate10HError(
            "STAGING_ADMIN_TOKEN is not set. Example:\n"
            "  export STAGING_ADMIN_TOKEN='...'\n"
            "  make gate10h-staging-rlhf ARGS=\"--stage evaluate --assume-synced --report\""
        )
    return token


def optional_prod_token() -> str | None:
    return os.environ.get("PROD_ADMIN_TOKEN", "").strip() or None


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Gate10HError(f"missing state file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Gate10HError("state file must be a JSON object")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def apply_staging_blueprint(
    path: Path,
    *,
    rlhf_enabled: bool,
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
    # One flag at a time: RLHF on ⇒ neural off.
    text2 = blueprint_set(text2, "FEATURE_NEURAL_BANDIT", "false")
    text2 = blueprint_set(text2, "FEATURE_RLHF_ROUTER", "true" if rlhf_enabled else "false")
    text2 = blueprint_set(text2, "FEATURE_KILL_SWITCH", "false")
    text2 = blueprint_set(text2, "FEATURE_AUTO_TUNING", "false")
    if blueprint_get(text2, "BANDIT_POLICY") is None:
        raise Gate10HError("BANDIT_POLICY missing from staging Blueprint")

    after = {
        "FEATURE_NEURAL_BANDIT": blueprint_get(text2, "FEATURE_NEURAL_BANDIT"),
        "FEATURE_RLHF_ROUTER": blueprint_get(text2, "FEATURE_RLHF_ROUTER"),
        "BANDIT_POLICY": blueprint_get(text2, "BANDIT_POLICY"),
        "FEATURE_KILL_SWITCH": blueprint_get(text2, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text2, "FEATURE_AUTO_TUNING"),
    }
    changed = text2 != text
    if dry_run:
        log(f"blueprint_dry_run before={json.dumps(before, sort_keys=True)}")
        log(f"blueprint_dry_run after={json.dumps(after, sort_keys=True)}")
        log("blueprint_dry_run=ok (no write)")
    else:
        path.write_text(text2, encoding="utf-8")
        log(f"blueprint_updated={path}")
        log(f"blueprint_after={json.dumps(after, sort_keys=True)}")
    return {"before": before, "after": after, "changed": changed, "dry_run": dry_run}


def validate_staging_blueprint(repo: Path, python: str, *, allow_rlhf: bool) -> None:
    cmd = [
        python,
        str(repo / "scripts" / "validate_render_blueprint.py"),
        "render.yaml",
        "--profile",
        "staging",
    ]
    if allow_rlhf:
        cmd.append("--allow-rlhf-router")
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        raise Gate10HError("staging Blueprint validation failed")


def policy_row(benchmark: dict[str, Any], name: str) -> dict[str, Any] | None:
    for row in benchmark.get("policies") or []:
        if isinstance(row, dict) and str(row.get("policy") or "").lower() == name:
            return row
    return None


def judge_benchmark(benchmark: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """PASS if rlhf is not materially worse than linucb on average_reward."""
    linucb = policy_row(benchmark, "linucb")
    rlhf = policy_row(benchmark, "rlhf")
    detail: dict[str, Any] = {
        "samples": benchmark.get("samples"),
        "linucb": linucb,
        "rlhf": rlhf,
    }
    if not linucb or not rlhf:
        detail["reason"] = "missing linucb or rlhf rows"
        return False, detail
    base = float(linucb.get("average_reward") or 0.0)
    cand = float(rlhf.get("average_reward") or 0.0)
    ok = cand >= base * 0.95
    detail["average_reward_linucb"] = base
    detail["average_reward_rlhf"] = cand
    detail["threshold"] = base * 0.95
    detail["reason"] = "ok" if ok else "rlhf_average_reward_below_95pct_linucb"
    return ok, detail


class StagingRlhfEvaluator:
    def __init__(
        self,
        *,
        repo: Path,
        staging_url: str,
        prod_url: str,
        state_path: Path,
        blueprint_path: Path,
        report_dir: Path,
        dry_run: bool,
        skip_prod_prereqs: bool,
        assume_synced: bool,
        soak_seconds: int,
        benchmark_limit: int,
        python: str,
        seed_before_smoke: bool = True,
    ) -> None:
        self.repo = repo
        self.staging_url = staging_url.rstrip("/")
        self.prod_url = prod_url.rstrip("/")
        self.state_path = state_path
        self.blueprint_path = blueprint_path
        self.report_dir = report_dir
        self.dry_run = dry_run
        self.skip_prod_prereqs = skip_prod_prereqs
        self.assume_synced = assume_synced
        self.soak_seconds = soak_seconds
        self.benchmark_limit = benchmark_limit
        self.python = python
        self.seed_before_smoke = seed_before_smoke
        self.results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gate": "10H_staging_rlhf",
            "dry_run": dry_run,
            "prerequisites": {"passed": False, "checks": []},
            "setup": {"passed": False, "steps": []},
            "evaluation": {"passed": False, "metrics": {}},
            "cleanup": {"passed": False, "steps": []},
        }

    def _check(self, name: str, ok: bool, message: str) -> bool:
        status = "PASS" if ok else "FAIL"
        log(f"  {name}: {status} — {message}")
        self.results["prerequisites"]["checks"].append(
            {"step": name, "status": status, "message": message}
        )
        return ok

    def check_prerequisites(self) -> bool:
        log("gate10h_staging_rlhf=check_prerequisites")
        checks_ok = True
        token: str | None = None
        try:
            token = require_staging_token()
        except Gate10HError as exc:
            if self.dry_run:
                checks_ok &= self._check("staging_token", True, f"skipped in dry-run ({exc})")
            else:
                checks_ok &= self._check("staging_token", False, str(exc))
                self.results["prerequisites"]["passed"] = False
                log("gate10h_staging_rlhf=check error")
                return False

        if token:
            try:
                health = http_json(f"{self.staging_url}/health")
                checks_ok &= self._check(
                    "staging_health", health.get("status") == "ok", str(health.get("status"))
                )
            except Gate10HError as exc:
                checks_ok &= self._check("staging_health", False, str(exc))
        else:
            checks_ok &= self._check("staging_health", True, "skipped (dry-run, no token)")

        try:
            state = load_state(self.state_path)
        except Gate10HError as exc:
            checks_ok &= self._check("state_file", False, str(exc))
            state = {}

        if state:
            e_ok = (
                bool(state.get("staging_drill_passed_at"))
                and bool(state.get("mock_router_ready_at"))
                and int(state.get("c4_percentage") or 0) == 100
            )
            c4_at = float(state.get("c4_set_at") or 0)
            soak_ok = c4_at > 0 and (time.time() - c4_at) >= self.soak_seconds
            checks_ok &= self._check(
                "gate_10e_state",
                e_ok and soak_ok,
                f"c4=100 soak={fmt_duration(time.time() - c4_at) if c4_at else 'n/a'}",
            )
            checks_ok &= self._check(
                "gate_10f_state",
                bool(state.get("gate10f_router_flip")),
                f"flip={bool(state.get('gate10f_router_flip'))}",
            )

        if self.skip_prod_prereqs:
            checks_ok &= self._check("gate_10g_prod", True, "skipped (--skip-prod-prereqs)")
        else:
            prod_token = optional_prod_token()
            if not prod_token:
                checks_ok &= self._check(
                    "gate_10g_prod",
                    False,
                    "set PROD_ADMIN_TOKEN or pass --skip-prod-prereqs",
                )
            else:
                try:
                    router = http_json(f"{self.prod_url}/admin/router-status", token=prod_token)
                    safety = http_json(f"{self.prod_url}/admin/safety/status", token=prod_token)
                    live_ok = (
                        router.get("active") is True
                        and str(router.get("mode") or "").lower() == "live"
                    )
                    env = safety.get("env") or {}
                    safe_ok = (
                        env.get("feature_kill_switch") is not True
                        and env.get("feature_auto_tuning") is not True
                    )
                    checks_ok &= self._check(
                        "gate_10g_prod",
                        live_ok and safe_ok,
                        f"active={router.get('active')} mode={router.get('mode')} "
                        f"kill={env.get('feature_kill_switch')} "
                        f"autotune={env.get('feature_auto_tuning')}",
                    )
                except Gate10HError as exc:
                    checks_ok &= self._check("gate_10g_prod", False, str(exc))

        if token:
            try:
                safety = http_json(f"{self.staging_url}/admin/safety/status", token=token)
                env = safety.get("env") or {}
                runtime = safety.get("runtime") or {}
                safe_ok = (
                    env.get("feature_kill_switch") is not True
                    and env.get("feature_auto_tuning") is not True
                    and runtime.get("tripped") is not True
                )
                checks_ok &= self._check(
                    "staging_safety",
                    safe_ok,
                    f"kill={env.get('feature_kill_switch')} "
                    f"autotune={env.get('feature_auto_tuning')} "
                    f"tripped={runtime.get('tripped')}",
                )
            except Gate10HError as exc:
                checks_ok &= self._check("staging_safety", False, str(exc))

            try:
                bandit = http_json(f"{self.staging_url}/admin/bandit/status", token=token)
                flags = bandit.get("flags") or {}
                rlhf = bandit.get("rlhf") or {}
                checks_ok &= self._check(
                    "staging_bandit",
                    True,
                    f"policy={bandit.get('policy')} flags.rlhf={flags.get('rlhf')} "
                    f"rlhf.ready={rlhf.get('ready')} samples={rlhf.get('sample_count')}",
                )
                if flags.get("neural") is True:
                    checks_ok &= self._check(
                        "neural_flag_off",
                        False,
                        "flags.neural=true — finish neural cleanup before RLHF drill",
                    )
            except Gate10HError as exc:
                checks_ok &= self._check("staging_bandit", False, str(exc))

        self.results["prerequisites"]["passed"] = checks_ok
        log(f"gate10h_staging_rlhf=check {'ok' if checks_ok else 'error'}")
        return checks_ok

    def setup_staging(self) -> bool:
        log("gate10h_staging_rlhf=setup")
        steps: list[dict[str, Any]] = []
        try:
            result = apply_staging_blueprint(
                self.blueprint_path,
                rlhf_enabled=True,
                dry_run=self.dry_run,
            )
            steps.append(
                {
                    "step": "blueprint_FEATURE_RLHF_ROUTER",
                    "status": "DRY_RUN" if self.dry_run else "PASS",
                    "message": json.dumps(result["after"], sort_keys=True),
                }
            )
            if not self.dry_run:
                validate_staging_blueprint(self.repo, self.python, allow_rlhf=True)
                steps.append(
                    {
                        "step": "validate_blueprint",
                        "status": "PASS",
                        "message": "--allow-rlhf-router",
                    }
                )
            self.results["setup"]["steps"] = steps
            self.results["setup"]["passed"] = True
            log("ACTION_REQUIRED:")
            log("  1) Commit/PR render.yaml (FEATURE_RLHF_ROUTER=true, neural=false)")
            log("  2) Render Sync staging Blueprint")
            log("  3) Wait until GET /admin/bandit/status → flags.rlhf=true")
            log(
                "  4) make gate10h-staging-rlhf "
                "ARGS='--stage evaluate --assume-synced --report'"
            )
            return True
        except Gate10HError as exc:
            steps.append({"step": "setup", "status": "FAIL", "message": str(exc)})
            self.results["setup"]["steps"] = steps
            self.results["setup"]["passed"] = False
            log(f"gate10h_staging_rlhf=error: {exc}")
            return False

    def switch_policy(self, policy: str, token: str) -> dict[str, Any]:
        if self.dry_run:
            log(f"[DRY RUN] would POST /admin/bandit/switch_policy policy={policy}")
            return {"policy": policy, "dry_run": True}
        return http_json(
            f"{self.staging_url}/admin/bandit/switch_policy",
            token=token,
            method="POST",
            body={"policy": policy},
        )

    def _staging_admin_env(self) -> dict[str, str]:
        env = os.environ.copy()
        token = (
            os.environ.get("STAGING_ADMIN_TOKEN", "").strip()
            or os.environ.get("ADMIN_API_TOKEN", "").strip()
        )
        if token:
            env["ADMIN_API_TOKEN"] = token
            env["STAGING_ADMIN_TOKEN"] = token
        return env

    def run_staging_seed(self) -> bool:
        if self.dry_run:
            log("[DRY RUN] would run scripts/staging_seed_mock.py")
            return True
        env = self._staging_admin_env()
        if not env.get("ADMIN_API_TOKEN"):
            log("staging_seed=error: missing STAGING_ADMIN_TOKEN")
            return False
        cmd = [
            self.python,
            str(self.repo / "scripts" / "staging_seed_mock.py"),
            "--api-url",
            self.staging_url,
            "--token-env",
            "ADMIN_API_TOKEN",
        ]
        log(f"$ {' '.join(cmd)}")
        result = subprocess.run(
            cmd, cwd=str(self.repo), text=True, capture_output=True, env=env
        )
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
        return result.returncode == 0

    def run_rlhf_smoke(self, *, token: str) -> tuple[bool, dict[str, Any]]:
        detail: dict[str, Any] = {}
        if self.dry_run:
            log("[DRY RUN] would run rlhf-focused staging smoke")
            return True, {"dry_run": True}
        try:
            health = http_json(f"{self.staging_url}/health")
            detail["health"] = health.get("status")
            if health.get("status") != "ok":
                return False, detail

            bandit = http_json(f"{self.staging_url}/admin/bandit/status", token=token)
            detail["policy"] = bandit.get("policy")
            detail["flags"] = bandit.get("flags")
            detail["rlhf"] = {
                "ready": (bandit.get("rlhf") or {}).get("ready"),
                "sample_count": (bandit.get("rlhf") or {}).get("sample_count"),
            }
            flags = bandit.get("flags") or {}
            if flags.get("rlhf") is not True:
                detail["reason"] = "flags.rlhf is not true"
                return False, detail
            if str(bandit.get("policy") or "").lower() != "rlhf":
                detail["reason"] = f"policy is {bandit.get('policy')}, expected rlhf"
                return False, detail

            search = http_json(f"{self.staging_url}/search?q=buds&limit=5")
            count = search.get("count")
            detail["search_count"] = count
            if not isinstance(count, int) or count < 1:
                detail["reason"] = "search returned no results after seed"
                return False, detail

            safety = http_json(f"{self.staging_url}/admin/safety/status", token=token)
            env = safety.get("env") or {}
            detail["safety"] = {
                "kill": env.get("feature_kill_switch"),
                "autotune": env.get("feature_auto_tuning"),
            }
            if env.get("feature_kill_switch") is True or env.get("feature_auto_tuning") is True:
                detail["reason"] = "kill/autotune unexpectedly enabled"
                return False, detail

            detail["reason"] = "ok"
            log(
                "rlhf_smoke=ok "
                f"policy=rlhf search_count={count} "
                f"rlhf.ready={detail['rlhf'].get('ready')}"
            )
            return True, detail
        except Gate10HError as exc:
            detail["reason"] = str(exc)
            return False, detail

    def evaluate(self) -> bool:
        log("gate10h_staging_rlhf=evaluate")
        metrics: dict[str, Any] = {}

        if self.dry_run:
            log("[DRY RUN] evaluate: switch rlhf → smoke → benchmark → judge → switch linucb")
            self.results["evaluation"]["passed"] = True
            self.results["evaluation"]["metrics"] = {"dry_run": True}
            return True

        token = require_staging_token()
        bandit = http_json(f"{self.staging_url}/admin/bandit/status", token=token)
        flags = bandit.get("flags") or {}
        if flags.get("rlhf") is not True and not self.assume_synced:
            raise Gate10HError(
                "staging flags.rlhf is not true — Sync Blueprint after --stage setup "
                "(or pass --assume-synced if already enabled)"
            )
        if flags.get("rlhf") is not True and self.assume_synced:
            raise Gate10HError(
                "flags.rlhf still false on staging after --assume-synced; Sync incomplete?"
            )

        try:
            train = http_json(
                f"{self.staging_url}/admin/bandit/train",
                token=token,
                method="POST",
                body={"limit": min(self.benchmark_limit, 5000)},
            )
            metrics["train"] = {
                k: train.get(k) for k in ("trained", "log_count", "sample_count") if k in train
            } or train
        except Gate10HError as exc:
            metrics["train_warning"] = str(exc)

        switched = self.switch_policy("rlhf", token)
        metrics["switch_rlhf"] = switched
        log(f"switch_policy={json.dumps(switched, sort_keys=True)}")

        time.sleep(2)
        status_after = http_json(f"{self.staging_url}/admin/bandit/status", token=token)
        metrics["bandit_after_switch"] = {
            "policy": status_after.get("policy"),
            "flags": status_after.get("flags"),
            "rlhf": status_after.get("rlhf"),
            "controls_routing": status_after.get("controls_routing"),
        }

        if self.seed_before_smoke:
            seed_ok = self.run_staging_seed()
            metrics["staging_seed"] = seed_ok
            if not seed_ok:
                self.switch_policy("linucb", token)
                self.results["evaluation"]["passed"] = False
                self.results["evaluation"]["metrics"] = metrics
                log("gate10h_staging_rlhf=error: staging seed failed")
                return False

        smoke_ok, smoke_detail = self.run_rlhf_smoke(token=token)
        metrics["rlhf_smoke"] = smoke_detail
        if not smoke_ok:
            self.switch_policy("linucb", token)
            self.results["evaluation"]["passed"] = False
            self.results["evaluation"]["metrics"] = metrics
            log("gate10h_staging_rlhf=error: smoke failed after rlhf switch")
            return False

        benchmark = http_json(
            f"{self.staging_url}/admin/benchmark/run",
            token=token,
            method="POST",
            body={"limit": self.benchmark_limit},
        )
        results = http_json(f"{self.staging_url}/admin/benchmark/results", token=token)
        metrics["benchmark"] = results or benchmark
        ok, judgment = judge_benchmark(metrics["benchmark"])
        metrics["judgment"] = judgment

        restore = self.switch_policy("linucb", token)
        metrics["switch_linucb"] = restore

        self.results["evaluation"]["passed"] = ok
        self.results["evaluation"]["metrics"] = metrics
        log(
            f"gate10h_staging_rlhf=evaluate {'ok' if ok else 'error'} "
            f"reason={judgment.get('reason')} "
            f"rlhf_reward={judgment.get('average_reward_rlhf')} "
            f"linucb_reward={judgment.get('average_reward_linucb')}"
        )
        return ok

    def cleanup(self) -> bool:
        log("gate10h_staging_rlhf=cleanup")
        steps: list[dict[str, Any]] = []
        try:
            if self.dry_run:
                steps.append(
                    {
                        "step": "switch_linucb",
                        "status": "DRY_RUN",
                        "message": "would switch policy=linucb",
                    }
                )
            else:
                token = require_staging_token()
                restored = self.switch_policy("linucb", token)
                steps.append(
                    {
                        "step": "switch_linucb",
                        "status": "PASS",
                        "message": json.dumps(restored, sort_keys=True),
                    }
                )

            result = apply_staging_blueprint(
                self.blueprint_path,
                rlhf_enabled=False,
                dry_run=self.dry_run,
            )
            steps.append(
                {
                    "step": "blueprint_FEATURE_RLHF_ROUTER=false",
                    "status": "DRY_RUN" if self.dry_run else "PASS",
                    "message": json.dumps(result["after"], sort_keys=True),
                }
            )
            if not self.dry_run:
                validate_staging_blueprint(self.repo, self.python, allow_rlhf=False)
            log("ACTION_REQUIRED: Sync staging Blueprint to clear FEATURE_RLHF_ROUTER")
            self.results["cleanup"]["steps"] = steps
            self.results["cleanup"]["passed"] = True
            return True
        except Gate10HError as exc:
            steps.append({"step": "cleanup", "status": "FAIL", "message": str(exc)})
            self.results["cleanup"]["steps"] = steps
            self.results["cleanup"]["passed"] = False
            log(f"gate10h_staging_rlhf=error: {exc}")
            return False

    def write_report(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.report_dir / f"gate10h_staging_rlhf_{stamp}.json"
        save_json(path, self.results)
        save_json(self.report_dir / "gate10h_staging_rlhf_latest.json", self.results)
        log(f"report_written={path}")
        return path


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10H staging RLHF Router drill")
    parser.add_argument(
        "--stage",
        choices=["check", "setup", "evaluate", "cleanup", "full"],
        default="check",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--skip-prod-prereqs", action="store_true")
    parser.add_argument("--assume-synced", action="store_true")
    parser.add_argument(
        "--staging-url",
        default=os.environ.get("STAGING_API_URL", DEFAULT_STAGING),
    )
    parser.add_argument("--prod-url", default=os.environ.get("API_URL", DEFAULT_PROD))
    parser.add_argument(
        "--state-file",
        default=str(repo / "artifacts" / "gate10e_rollout_state.json"),
    )
    parser.add_argument("--blueprint", default=str(repo / "render.yaml"))
    parser.add_argument("--report-dir", default=str(repo / "artifacts"))
    parser.add_argument(
        "--soak-seconds",
        type=int,
        default=int(os.environ.get("GATE10E_SOAK_SECONDS", str(DEFAULT_SOAK))),
    )
    parser.add_argument("--benchmark-limit", type=int, default=2000)
    parser.add_argument("--no-seed", action="store_true")
    parser.add_argument("--python", default="")
    parser.add_argument("--repo-root", default=str(repo))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root)
    python = args.python or os.environ.get("PYTHON") or str(repo / ".venv" / "bin" / "python")
    if not Path(python).exists():
        python = sys.executable

    evaluator = StagingRlhfEvaluator(
        repo=repo,
        staging_url=args.staging_url,
        prod_url=args.prod_url,
        state_path=Path(args.state_file),
        blueprint_path=Path(args.blueprint),
        report_dir=Path(args.report_dir),
        dry_run=args.dry_run,
        skip_prod_prereqs=args.skip_prod_prereqs,
        assume_synced=args.assume_synced,
        soak_seconds=args.soak_seconds,
        benchmark_limit=args.benchmark_limit,
        python=python,
        seed_before_smoke=not args.no_seed,
    )

    log(f"gate10h_staging_rlhf=start stage={args.stage} dry_run={args.dry_run}")
    try:
        ok = False
        if args.stage == "check":
            ok = evaluator.check_prerequisites()
        elif args.stage == "setup":
            if not evaluator.check_prerequisites() and not args.dry_run:
                raise Gate10HError("prerequisites failed")
            ok = evaluator.setup_staging()
        elif args.stage == "evaluate":
            ok = evaluator.evaluate()
        elif args.stage == "cleanup":
            ok = evaluator.cleanup()
        elif args.stage == "full":
            if not evaluator.check_prerequisites() and not args.dry_run:
                raise Gate10HError("prerequisites failed")
            ok = evaluator.setup_staging()
            if not ok:
                raise Gate10HError("setup failed")
            if args.dry_run:
                ok = evaluator.evaluate() and evaluator.cleanup()
            else:
                log(
                    "full_mode: Blueprint updated locally. "
                    "Sync staging, then re-run --stage evaluate --assume-synced "
                    "and --stage cleanup. Stopping before live switch."
                )
                ok = True
        else:
            raise Gate10HError(f"unknown stage {args.stage}")

        if args.report:
            evaluator.write_report()
        return 0 if ok else 1
    except Gate10HError as exc:
        log(f"gate10h_staging_rlhf=error: {exc}")
        if args.report:
            evaluator.results["error"] = str(exc)
            evaluator.write_report()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
