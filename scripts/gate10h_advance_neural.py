#!/usr/bin/env python3
"""Gate 10H: advance production neural soak n10 → n25 → n50 → n100.

Gates on:
  1) current phase soak ≥ 24h (from artifacts/gate10h_prod_neural_state.json)
  2) latest soak monitor report for that phase status=PASS
     (artifacts/gate10h_soak_report_{phase}_latest.json)

Then records the next soak checkpoint (delegates timing to prod neural state).
``POST /admin/bandit/switch_policy`` only accepts ``{"policy": ...}`` — there is
**no traffic percentage** on that route. Policy stays ``neural``. Optional
``--mutate-canary`` sets ``/admin/canary/config`` percentage (off by default;
live router is already at 100% post-10G).

Usage:
  export PROD_ADMIN_TOKEN=...

  .venv/bin/python scripts/gate10h_advance_neural.py --stage status
  .venv/bin/python scripts/gate10h_advance_neural.py --phase n10 --target n25 --dry-run
  .venv/bin/python scripts/gate10h_advance_neural.py --phase n10 --target n25 --report
  .venv/bin/python scripts/gate10h_advance_neural.py --phase n10 --target n25 --force
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROD = "https://dealhunter-production-api.onrender.com"
USER_AGENT = "SaveIQ-Gate10H-AdvanceNeural/1.0"
PHASES = ("n10", "n25", "n50", "n100")
PHASE_PCT = {"n10": 10, "n25": 25, "n50": 50, "n100": 100}
DEFAULT_SOAK = 24 * 60 * 60
CANONICAL_STATE = "artifacts/gate10h_prod_neural_state.json"
ALIAS_STATE = "artifacts/gate10h_neural_state.json"


class AdvanceError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m"


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def require_prod_token() -> str:
    token = os.environ.get("PROD_ADMIN_TOKEN", "").strip()
    if not token:
        raise AdvanceError("PROD_ADMIN_TOKEN required")
    return token


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
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise AdvanceError(f"{method} {url} -> HTTP {exc.code}: {err[:400]}") from exc
    parsed = json.loads(payload) if payload else {}
    if not isinstance(parsed, dict):
        raise AdvanceError(f"{url} did not return a JSON object")
    return parsed


def sync_alias_state(canonical: Path, alias: Path) -> None:
    if canonical.is_file():
        alias.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(canonical, alias)


def load_monitor_report(repo: Path, phase: str) -> dict[str, Any]:
    path = repo / "artifacts" / f"gate10h_soak_report_{phase}_latest.json"
    if not path.is_file():
        raise AdvanceError(
            f"missing soak monitor report {path} — run "
            f"scripts/gate10h_monitor_soak.py --phase {phase} --once --report"
        )
    return load_json(path)


def phase_elapsed(state: dict[str, Any], phase: str) -> tuple[float, dict[str, Any]]:
    meta = (state.get("phases") or {}).get(phase) or {}
    started = float(meta.get("started_at_epoch") or 0)
    if started <= 0:
        raise AdvanceError(f"phase {phase} never started (start-soak first)")
    return time.time() - started, meta


def evaluate_ready(
    *,
    repo: Path,
    state: dict[str, Any],
    current: str,
    target: str,
    soak_seconds: float,
    force: bool,
    force_soak: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    if PHASES.index(target) != PHASES.index(current) + 1:
        raise AdvanceError(f"target {target} is not the next phase after {current}")

    elapsed, meta = phase_elapsed(state, current)
    soak_ok = elapsed >= soak_seconds or force_soak
    checks.append(
        {
            "name": "soak_24h",
            "ok": soak_ok,
            "detail": (
                f"{current} elapsed={fmt_duration(elapsed)} "
                f"need={fmt_duration(soak_seconds)}"
                + (" (forced)" if force_soak and elapsed < soak_seconds else "")
            ),
        }
    )

    try:
        report = load_monitor_report(repo, current)
        monitor_ok = str(report.get("status") or "").upper() == "PASS" or force
        checks.append(
            {
                "name": "monitor_report",
                "ok": monitor_ok,
                "detail": (
                    f"status={report.get('status')} ticks={report.get('ticks')} "
                    f"breaches={report.get('breaches')} "
                    f"checked_at={report.get('checked_at')}"
                    + (" (forced)" if force and str(report.get('status')).upper() != "PASS" else "")
                ),
            }
        )
    except AdvanceError as exc:
        if force:
            checks.append({"name": "monitor_report", "ok": True, "detail": f"missing; forced ({exc})"})
        else:
            checks.append({"name": "monitor_report", "ok": False, "detail": str(exc)})

    current_phase = state.get("current_phase")
    checks.append(
        {
            "name": "current_phase",
            "ok": current_phase == current or force,
            "detail": f"state.current_phase={current_phase} expected={current}",
        }
    )
    passed = all(c["ok"] is not False for c in checks)
    return passed, checks


class AdvanceNeural:
    def __init__(
        self,
        *,
        repo: Path,
        api_url: str,
        dry_run: bool,
        soak_seconds: float,
        mutate_canary: bool,
        report_dir: Path,
    ) -> None:
        self.repo = repo
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self.soak_seconds = soak_seconds
        self.mutate_canary = mutate_canary
        self.canonical = repo / CANONICAL_STATE
        self.alias = repo / ALIAS_STATE
        self.report_dir = report_dir
        self.results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gate": "10H_advance_neural",
            "dry_run": dry_run,
            "checks": [],
        }

    def load_state(self) -> dict[str, Any]:
        state = load_json(self.canonical)
        if not state:
            state = load_json(self.alias)
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(self.canonical, state)
        sync_alias_state(self.canonical, self.alias)
        log(f"state_written={self.canonical}")
        log(f"state_alias={self.alias}")

    def status(self) -> bool:
        log("gate10h_advance=status")
        state = self.load_state()
        token = require_prod_token()
        bandit = http_json(f"{self.api_url}/admin/bandit/status", token=token)
        current = state.get("current_phase") or "n10"
        log(f"policy={bandit.get('policy')} flags={bandit.get('flags')}")
        log(f"current_phase={current}")
        now = time.time()
        for name in PHASES:
            meta = (state.get("phases") or {}).get(name) or {}
            started = float(meta.get("started_at_epoch") or 0)
            if not started:
                log(f"  {name}: not_started")
                continue
            elapsed = now - started
            log(
                f"  {name}: elapsed={fmt_duration(elapsed)} "
                f"completed={meta.get('completed')} started={meta.get('started_at')}"
            )
        self.results["status"] = {"current_phase": current, "bandit": bandit.get("flags")}
        return True

    def advance(self, *, current: str, target: str, force: bool, force_soak: bool) -> bool:
        log(f"gate10h_advance={current}->{target} dry_run={self.dry_run} force={force}")
        state = self.load_state()
        if not state:
            raise AdvanceError(f"missing state {self.canonical} — run gate10h_prod_neural.py first")

        passed, checks = evaluate_ready(
            repo=self.repo,
            state=state,
            current=current,
            target=target,
            soak_seconds=self.soak_seconds,
            force=force,
            force_soak=force_soak,
        )
        self.results["checks"] = checks
        for item in checks:
            status = "PASS" if item["ok"] else "FAIL"
            log(f"  {status} {item['name']}: {item['detail']}")
        if not passed:
            log("ADVANCE_BLOCKED: soak/monitor not PASS — do not advance; notify operator")
            self.results["advanced"] = False
            return False

        if self.dry_run:
            log(
                f"[DRY RUN] would mark {current} complete and start {target} "
                f"(label={PHASE_PCT[target]}%; policy stays neural; "
                f"canary_mutate={self.mutate_canary})"
            )
            self.results["advanced"] = False
            self.results["dry_run"] = True
            return True

        token = require_prod_token()
        switched = http_json(
            f"{self.api_url}/admin/bandit/switch_policy",
            token=token,
            method="POST",
            body={"policy": "neural"},
        )
        log(f"switch_policy={json.dumps(switched, sort_keys=True)} (no traffic % on this route)")

        if self.mutate_canary:
            canary = http_json(
                f"{self.api_url}/admin/canary/config",
                token=token,
                method="POST",
                body={"enabled": True, "percentage": PHASE_PCT[target]},
            )
            log(f"canary_mutated={json.dumps(canary, sort_keys=True)}")
        else:
            log(
                f"soak_checkpoint={target} target_label={PHASE_PCT[target]}% "
                "(canary not mutated)"
            )

        now = time.time()
        phases = state.setdefault("phases", {})
        prev = phases.get(current) or {}
        prev["completed"] = True
        prev["completed_at"] = datetime.now(timezone.utc).isoformat()
        prev["soak_seconds"] = now - float(prev.get("started_at_epoch") or now)
        phases[current] = prev
        phases[target] = {
            "target_pct": PHASE_PCT[target],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "started_at_epoch": now,
            "completed": False,
            "mutate_canary": self.mutate_canary,
        }
        state["current_phase"] = target
        state["policy"] = "neural"
        self.save_state(state)
        self.results["advanced"] = True
        self.results["from"] = current
        self.results["to"] = target
        log(f"gate10h_advance=ok {current}->{target}")
        log(
            "Update docs/GATE_10H_NEURAL_RLHF_CHECKLIST.md soak checkbox for "
            f"{current} then start monitor --phase {target}"
        )
        return True

    def write_report(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.report_dir / f"gate10h_advance_neural_{stamp}.json"
        save_json(path, self.results)
        save_json(self.report_dir / "gate10h_advance_neural_latest.json", self.results)
        log(f"report_written={path}")
        return path


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10H advance neural soak phase")
    parser.add_argument("--stage", choices=["status", "advance"], default="advance")
    parser.add_argument("--phase", choices=PHASES, default="")
    parser.add_argument("--target", choices=PHASES, default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--force", action="store_true", help="Skip monitor PASS requirement")
    parser.add_argument("--force-soak", action="store_true", help="Skip 24h soak requirement")
    parser.add_argument(
        "--mutate-canary",
        action="store_true",
        help="Also POST /admin/canary/config to phase percentage",
    )
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_PROD))
    parser.add_argument(
        "--soak-seconds",
        type=float,
        default=float(os.environ.get("GATE10H_SOAK_SECONDS", str(DEFAULT_SOAK))),
    )
    parser.add_argument("--report-dir", default=str(repo / "artifacts"))
    parser.add_argument("--repo-root", default=str(repo))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root)
    runner = AdvanceNeural(
        repo=repo,
        api_url=args.api_url,
        dry_run=args.dry_run,
        soak_seconds=args.soak_seconds,
        mutate_canary=args.mutate_canary,
        report_dir=Path(args.report_dir),
    )
    try:
        ok = False
        if args.stage == "status":
            ok = runner.status()
        else:
            if not args.phase or not args.target:
                raise AdvanceError("--phase and --target required (e.g. --phase n10 --target n25)")
            ok = runner.advance(
                current=args.phase,
                target=args.target,
                force=args.force,
                force_soak=args.force_soak,
            )
        if args.report:
            runner.write_report()
        return 0 if ok else 1
    except AdvanceError as exc:
        log(f"gate10h_advance=error: {exc}")
        if args.report:
            runner.results["error"] = str(exc)
            runner.write_report()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
