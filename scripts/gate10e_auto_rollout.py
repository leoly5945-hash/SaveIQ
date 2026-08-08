#!/usr/bin/env python3
"""Background Gate 10E auto-rollout daemon.

Waits for C3 24h soak → advances C4 → waits C4 soak → optionally enables
mock-router phase → writes/updates the rollout report.

Safety
------
- Never passes --force to gate10e_rollout.py
- Never enables production FEATURE_KILL_SWITCH / FEATURE_AUTO_TUNING
- On soak monitor BREACH: rollback canary and stop
- Secrets only from PROD_ADMIN_TOKEN (or ADMIN_API_TOKEN)

Usage
-----
  export PROD_ADMIN_TOKEN=...

  # Foreground daemon (Ctrl+C safe; resumes from state file)
  .venv/bin/python scripts/gate10e_auto_rollout.py --daemon

  # Background
  nohup .venv/bin/python scripts/gate10e_auto_rollout.py --daemon \\
    > artifacts/gate10e_auto_rollout.log 2>&1 &
  echo $! > artifacts/gate10e_auto_rollout.pid

  # Status only (no wait / no mutate)
  .venv/bin/python scripts/gate10e_auto_rollout.py --status

  # Stop after C4 is set (do not wait C4 soak / mock)
  .venv/bin/python scripts/gate10e_auto_rollout.py --daemon --until c4

  # After C4 soak, wait for operator before mock (default)
  .venv/bin/python scripts/gate10e_auto_rollout.py --daemon --until mock --wait-for-mock

  # After C4 soak, auto-run mock_router phase
  .venv/bin/python scripts/gate10e_auto_rollout.py --daemon --until mock --auto-mock
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_API = "https://dealhunter-production-api.onrender.com"
DEFAULT_WEB = "https://dealhunter-production-web.onrender.com"
DEFAULT_SOAK = 24 * 60 * 60
USER_AGENT = "SaveIQ-Gate10E-AutoRollout/1.0"


@dataclass
class DaemonState:
    version: int = 1
    started_at: float | None = None
    stopped_at: float | None = None
    last_tick_at: float | None = None
    last_phase: str | None = None
    last_monitor: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    exit_reason: str | None = None

    @classmethod
    def load(cls, path: Path) -> DaemonState:
        if not path.is_file():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            version=int(raw.get("version") or 1),
            started_at=raw.get("started_at"),
            stopped_at=raw.get("stopped_at"),
            last_tick_at=raw.get("last_tick_at"),
            last_phase=raw.get("last_phase"),
            last_monitor=dict(raw.get("last_monitor") or {}),
            events=list(raw.get("events") or []),
            finished=bool(raw.get("finished")),
            exit_reason=raw.get("exit_reason"),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def event(self, name: str, **extra: Any) -> None:
        self.events.append({"ts": time.time(), "event": name, **extra})
        self.events = self.events[-500:]


class AutoRolloutError(RuntimeError):
    pass


def log(msg: str, *, log_file: Path | None = None) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def require_prod_token() -> str:
    token = (
        os.environ.get("PROD_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
    )
    if not token:
        raise AutoRolloutError(
            "PROD_ADMIN_TOKEN is required (or ADMIN_API_TOKEN) for auto-rollout mutations"
        )
    return token


def load_rollout_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def soak_info(
    rollout_state: dict[str, Any], *, phase: str, soak_seconds: int
) -> dict[str, Any]:
    key = "c3_set_at" if phase == "c3" else "c4_set_at"
    started = rollout_state.get(key)
    if not started:
        return {
            "phase": phase,
            "started": False,
            "complete": False,
            "remaining_s": float(soak_seconds),
            "elapsed_s": 0.0,
        }
    started_f = float(started)
    elapsed = time.time() - started_f
    remaining = max(0.0, float(soak_seconds) - elapsed)
    return {
        "phase": phase,
        "started": True,
        "started_at": started_f,
        "elapsed_s": elapsed,
        "remaining_s": remaining,
        "complete": remaining <= 0,
        "percentage": rollout_state.get(
            "c3_percentage" if phase == "c3" else "c4_percentage"
        ),
    }


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_file: Path | None,
) -> subprocess.CompletedProcess[str]:
    log(f"$ {' '.join(cmd)}", log_file=log_file)
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, env=env)
    if result.stdout:
        print(
            result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True
        )
        if log_file is not None:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(result.stdout)
                if not result.stdout.endswith("\n"):
                    handle.write("\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
            flush=True,
        )
        if log_file is not None:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(result.stderr)
                if not result.stderr.endswith("\n"):
                    handle.write("\n")
    return result


def run_monitor(
    *,
    python: str,
    repo: Path,
    phase: str,
    api_url: str,
    state_file: Path,
    log_file: Path | None,
    env: dict[str, str],
) -> dict[str, Any]:
    cmd = [
        python,
        str(repo / "scripts" / "gate10e_soak_monitor.py"),
        "--phase",
        phase,
        "--api-url",
        api_url,
        "--state-file",
        str(state_file),
    ]
    result = run_cmd(cmd, cwd=repo, env=env, log_file=log_file)
    payload: dict[str, Any] = {
        "exit_code": result.returncode,
        "breach": result.returncode == 2,
        "ok": result.returncode == 0,
    }
    # Parse last JSON object from stdout if present.
    text = result.stdout or ""
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            payload["record"] = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            payload["parse_error"] = True
    return payload


def run_rollout_phase(
    *,
    python: str,
    repo: Path,
    phase: str,
    api_url: str,
    web_url: str,
    state_file: Path,
    soak_seconds: int,
    log_file: Path | None,
    env: dict[str, str],
) -> None:
    cmd = [
        python,
        str(repo / "scripts" / "gate10e_rollout.py"),
        "--phase",
        phase,
        "--prod-api-url",
        api_url,
        "--prod-web-url",
        web_url,
        "--state-file",
        str(state_file),
        "--soak-seconds",
        str(soak_seconds),
        # intentionally no --force
    ]
    result = run_cmd(cmd, cwd=repo, env=env, log_file=log_file)
    if result.returncode != 0:
        raise AutoRolloutError(
            f"rollout phase {phase} failed (exit {result.returncode})"
        )


def write_report(
    *,
    report_path: Path,
    rollout_state: dict[str, Any],
    daemon: DaemonState,
    soak_seconds: int,
) -> None:
    c3 = soak_info(rollout_state, phase="c3", soak_seconds=soak_seconds)
    c4 = soak_info(rollout_state, phase="c4", soak_seconds=soak_seconds)
    mock_at = rollout_state.get("mock_router_ready_at")
    lines = [
        "# Gate 10E Rollout Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Daemon exit: {daemon.exit_reason or ('running' if not daemon.finished else 'finished')}",
        "",
        "## Phase status",
        "",
        "| Phase | Status | Detail |",
        "| --- | --- | --- |",
        f"| Staging drill | {'PASS' if rollout_state.get('staging_drill_passed_at') else 'UNKNOWN'} | ts={rollout_state.get('staging_drill_passed_at')} |",
        f"| C3 (25%) | {'COMPLETE' if c3.get('complete') else ('SOAKING' if c3.get('started') else 'PENDING')} | remaining={fmt_duration(float(c3.get('remaining_s') or 0))} |",
        f"| C4 (100%) | {'COMPLETE' if c4.get('complete') else ('SOAKING' if c4.get('started') else 'PENDING')} | remaining={fmt_duration(float(c4.get('remaining_s') or 0))} |",
        f"| Mock router | {'READY' if mock_at else 'PENDING'} | ts={mock_at} |",
        "",
        "## Safety",
        "",
        "- Production kill/autotune env must remain OFF (enforced by rollout script).",
        "- Auto-rollout never uses `--force`.",
        "- Breach handling: canary rollback via `--phase rollback`.",
        "",
        "## Daemon events (latest)",
        "",
    ]
    for event in daemon.events[-30:]:
        ts = datetime.fromtimestamp(
            float(event.get("ts") or 0), tz=timezone.utc
        ).isoformat()
        name = event.get("event")
        detail = {k: v for k, v in event.items() if k not in {"ts", "event"}}
        lines.append(f"- `{ts}` **{name}** {json.dumps(detail, sort_keys=True)}")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("- `artifacts/gate10e_rollout_state.json` — phase clocks")
    lines.append("- `artifacts/gate10e_auto_rollout_state.json` — daemon state")
    lines.append("- `artifacts/gate10e_auto_rollout.log` — daemon log")
    lines.append("- `artifacts/gate10e_soak_monitor.jsonl` — soak samples")
    lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class StopRequested(Exception):
    pass


_STOP = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _STOP
    _STOP = True
    print(f"signal={signum} stop_requested=true", flush=True)


def sleep_interruptible(seconds: float) -> None:
    end = time.time() + max(0.0, seconds)
    while time.time() < end:
        if _STOP:
            raise StopRequested("stop requested")
        time.sleep(min(5.0, end - time.time()))


def print_status(
    *,
    rollout_state: dict[str, Any],
    soak_seconds: int,
    log_file: Path | None,
) -> None:
    c3 = soak_info(rollout_state, phase="c3", soak_seconds=soak_seconds)
    c4 = soak_info(rollout_state, phase="c4", soak_seconds=soak_seconds)
    log(
        "status "
        f"c3_started={c3['started']} c3_complete={c3['complete']} "
        f"c3_remaining={fmt_duration(float(c3['remaining_s']))} "
        f"c4_started={c4['started']} c4_complete={c4['complete']} "
        f"c4_remaining={fmt_duration(float(c4['remaining_s']))} "
        f"mock={bool(rollout_state.get('mock_router_ready_at'))}",
        log_file=log_file,
    )


def daemon_loop(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root)
    python = (
        args.python
        or os.environ.get("PYTHON")
        or str(repo / ".venv" / "bin" / "python")
    )
    if not Path(python).exists():
        python = sys.executable

    state_file = Path(args.state_file)
    daemon_state_path = Path(args.daemon_state_file)
    log_file = Path(args.log_file)
    report_path = Path(args.report_file)
    pid_file = Path(args.pid_file)

    daemon = DaemonState.load(daemon_state_path)
    daemon.started_at = daemon.started_at or time.time()
    daemon.finished = False
    daemon.exit_reason = None
    daemon.event("daemon_start", until=args.until, auto_mock=args.auto_mock)
    daemon.save(daemon_state_path)

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()) + "\n", encoding="utf-8")

    env = os.environ.copy()
    # Ensure production smoke/rollout see the token under ADMIN_API_TOKEN too.
    token = require_prod_token()
    env["PROD_ADMIN_TOKEN"] = token
    env["ADMIN_API_TOKEN"] = token

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log(
        f"auto_rollout=start until={args.until} poll={args.poll_seconds}s "
        f"soak={args.soak_seconds}s auto_mock={args.auto_mock}",
        log_file=log_file,
    )

    try:
        while True:
            if _STOP:
                raise StopRequested("stop requested")

            rollout_state = load_rollout_state(state_file)
            print_status(
                rollout_state=rollout_state,
                soak_seconds=args.soak_seconds,
                log_file=log_file,
            )
            daemon.last_tick_at = time.time()

            c3 = soak_info(rollout_state, phase="c3", soak_seconds=args.soak_seconds)
            c4 = soak_info(rollout_state, phase="c4", soak_seconds=args.soak_seconds)

            # Determine active soak phase to monitor.
            if c4["started"] and not c4["complete"]:
                monitor_phase = "c4"
            elif c3["started"] and not c3["complete"]:
                monitor_phase = "c3"
            elif c4["started"] and c4["complete"]:
                monitor_phase = "c4"
            else:
                monitor_phase = "c3"

            monitor = run_monitor(
                python=python,
                repo=repo,
                phase=monitor_phase,
                api_url=args.prod_api_url,
                state_file=state_file,
                log_file=log_file,
                env=env,
            )
            daemon.last_monitor = monitor
            daemon.last_phase = monitor_phase
            daemon.event("monitor", phase=monitor_phase, breach=monitor.get("breach"))

            if monitor.get("breach"):
                log("BREACH detected — rolling back canary", log_file=log_file)
                daemon.event("breach_rollback", phase=monitor_phase)
                run_rollout_phase(
                    python=python,
                    repo=repo,
                    phase="rollback",
                    api_url=args.prod_api_url,
                    web_url=args.prod_web_url,
                    state_file=state_file,
                    soak_seconds=args.soak_seconds,
                    log_file=log_file,
                    env=env,
                )
                daemon.finished = True
                daemon.exit_reason = "rolled_back_on_breach"
                daemon.stopped_at = time.time()
                daemon.save(daemon_state_path)
                write_report(
                    report_path=report_path,
                    rollout_state=load_rollout_state(state_file),
                    daemon=daemon,
                    soak_seconds=args.soak_seconds,
                )
                log(
                    "auto_rollout=stopped reason=rolled_back_on_breach",
                    log_file=log_file,
                )
                return 2

            rollout_state = load_rollout_state(state_file)
            c3 = soak_info(rollout_state, phase="c3", soak_seconds=args.soak_seconds)
            c4 = soak_info(rollout_state, phase="c4", soak_seconds=args.soak_seconds)

            # Advance C3 soak → C4
            if c3["started"] and c3["complete"] and not c4["started"]:
                log("C3 soak complete → running soak_c3 + c4", log_file=log_file)
                run_rollout_phase(
                    python=python,
                    repo=repo,
                    phase="soak_c3",
                    api_url=args.prod_api_url,
                    web_url=args.prod_web_url,
                    state_file=state_file,
                    soak_seconds=args.soak_seconds,
                    log_file=log_file,
                    env=env,
                )
                run_rollout_phase(
                    python=python,
                    repo=repo,
                    phase="c4",
                    api_url=args.prod_api_url,
                    web_url=args.prod_web_url,
                    state_file=state_file,
                    soak_seconds=args.soak_seconds,
                    log_file=log_file,
                    env=env,
                )
                daemon.event("c4_advanced")
                daemon.save(daemon_state_path)
                write_report(
                    report_path=report_path,
                    rollout_state=load_rollout_state(state_file),
                    daemon=daemon,
                    soak_seconds=args.soak_seconds,
                )
                if args.until == "c4":
                    daemon.finished = True
                    daemon.exit_reason = "until_c4_reached"
                    daemon.stopped_at = time.time()
                    daemon.save(daemon_state_path)
                    log("auto_rollout=ok until=c4", log_file=log_file)
                    return 0
                # continue into C4 soak
                sleep_interruptible(float(args.poll_seconds))
                continue

            # C4 soak complete → mock
            rollout_state = load_rollout_state(state_file)
            c4 = soak_info(rollout_state, phase="c4", soak_seconds=args.soak_seconds)
            mock_ready = bool(rollout_state.get("mock_router_ready_at"))

            if c4["started"] and c4["complete"] and not mock_ready:
                log("C4 soak complete", log_file=log_file)
                run_rollout_phase(
                    python=python,
                    repo=repo,
                    phase="soak_c4",
                    api_url=args.prod_api_url,
                    web_url=args.prod_web_url,
                    state_file=state_file,
                    soak_seconds=args.soak_seconds,
                    log_file=log_file,
                    env=env,
                )
                if args.auto_mock:
                    log("auto-mock enabled → running mock_router", log_file=log_file)
                    run_rollout_phase(
                        python=python,
                        repo=repo,
                        phase="mock_router",
                        api_url=args.prod_api_url,
                        web_url=args.prod_web_url,
                        state_file=state_file,
                        soak_seconds=args.soak_seconds,
                        log_file=log_file,
                        env=env,
                    )
                    daemon.event("mock_router_done")
                else:
                    log(
                        "C4 soak done — waiting for operator mock "
                        "(re-run with --auto-mock, or: "
                        "scripts/gate10e_rollout.py --phase mock_router)",
                        log_file=log_file,
                    )
                    daemon.event("awaiting_mock_operator")
                    daemon.finished = True
                    daemon.exit_reason = "awaiting_mock"
                    daemon.stopped_at = time.time()
                    daemon.save(daemon_state_path)
                    write_report(
                        report_path=report_path,
                        rollout_state=load_rollout_state(state_file),
                        daemon=daemon,
                        soak_seconds=args.soak_seconds,
                    )
                    return 0

                daemon.finished = True
                daemon.exit_reason = "complete"
                daemon.stopped_at = time.time()
                daemon.save(daemon_state_path)
                write_report(
                    report_path=report_path,
                    rollout_state=load_rollout_state(state_file),
                    daemon=daemon,
                    soak_seconds=args.soak_seconds,
                )
                log("auto_rollout=ok complete", log_file=log_file)
                return 0

            if mock_ready and args.until in {"mock", "report", "all"}:
                daemon.finished = True
                daemon.exit_reason = "already_complete"
                daemon.stopped_at = time.time()
                daemon.save(daemon_state_path)
                write_report(
                    report_path=report_path,
                    rollout_state=rollout_state,
                    daemon=daemon,
                    soak_seconds=args.soak_seconds,
                )
                log("auto_rollout=ok already_complete", log_file=log_file)
                return 0

            # Still soaking — sleep until next poll (cap sleep to remaining soak).
            remaining = float(
                c4["remaining_s"]
                if c4["started"] and not c4["complete"]
                else c3["remaining_s"]
            )
            sleep_for = min(float(args.poll_seconds), max(5.0, remaining + 5.0))
            log(
                f"sleeping {fmt_duration(sleep_for)} "
                f"(poll={fmt_duration(float(args.poll_seconds))})",
                log_file=log_file,
            )
            daemon.save(daemon_state_path)
            write_report(
                report_path=report_path,
                rollout_state=rollout_state,
                daemon=daemon,
                soak_seconds=args.soak_seconds,
            )
            sleep_interruptible(sleep_for)

    except StopRequested as exc:
        daemon.finished = True
        daemon.exit_reason = str(exc)
        daemon.stopped_at = time.time()
        daemon.event("stopped", reason=str(exc))
        daemon.save(daemon_state_path)
        write_report(
            report_path=report_path,
            rollout_state=load_rollout_state(state_file),
            daemon=daemon,
            soak_seconds=args.soak_seconds,
        )
        log(f"auto_rollout=stopped reason={exc}", log_file=log_file)
        return 130
    except AutoRolloutError as exc:
        daemon.finished = True
        daemon.exit_reason = str(exc)
        daemon.stopped_at = time.time()
        daemon.event("error", message=str(exc))
        daemon.save(daemon_state_path)
        write_report(
            report_path=report_path,
            rollout_state=load_rollout_state(state_file),
            daemon=daemon,
            soak_seconds=args.soak_seconds,
        )
        log(f"auto_rollout=error: {exc}", log_file=log_file)
        return 1
    finally:
        try:
            if pid_file.is_file() and pid_file.read_text(
                encoding="utf-8"
            ).strip() == str(os.getpid()):
                pid_file.unlink(missing_ok=True)
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    repo_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Gate 10E background auto-rollout (C3 soak → C4 → C4 soak → mock)"
    )
    parser.add_argument(
        "--daemon", action="store_true", help="Run wait/monitor/advance loop"
    )
    parser.add_argument(
        "--status", action="store_true", help="Print soak status and exit"
    )
    parser.add_argument(
        "--until",
        choices=("c4", "mock", "report", "all"),
        default="mock",
        help="Stop condition (default: mock phase gate)",
    )
    parser.add_argument(
        "--auto-mock",
        action="store_true",
        help="After C4 soak, automatically run mock_router (default: wait for operator)",
    )
    parser.add_argument(
        "--wait-for-mock",
        action="store_true",
        help="Explicit alias for default: stop after C4 soak and wait for operator mock",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=int(os.environ.get("GATE10E_POLL_SECONDS", "300")),
        help="Monitor poll interval while soaking (default 300s)",
    )
    parser.add_argument(
        "--soak-seconds",
        type=int,
        default=int(os.environ.get("GATE10E_SOAK_SECONDS", str(DEFAULT_SOAK))),
    )
    parser.add_argument(
        "--prod-api-url", default=os.environ.get("API_URL", DEFAULT_API)
    )
    parser.add_argument(
        "--prod-web-url", default=os.environ.get("WEB_URL", DEFAULT_WEB)
    )
    parser.add_argument(
        "--state-file",
        default=str(repo_default / "artifacts" / "gate10e_rollout_state.json"),
    )
    parser.add_argument(
        "--daemon-state-file",
        default=str(repo_default / "artifacts" / "gate10e_auto_rollout_state.json"),
    )
    parser.add_argument(
        "--log-file",
        default=str(repo_default / "artifacts" / "gate10e_auto_rollout.log"),
    )
    parser.add_argument(
        "--pid-file",
        default=str(repo_default / "artifacts" / "gate10e_auto_rollout.pid"),
    )
    parser.add_argument(
        "--report-file",
        default=str(repo_default / "docs" / "GATE_10E_ROLLOUT_REPORT.md"),
    )
    parser.add_argument("--repo-root", default=str(repo_default))
    parser.add_argument("--python", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.wait_for_mock:
        args.auto_mock = False

    if args.status and not args.daemon:
        rollout_state = load_rollout_state(Path(args.state_file))
        print_status(
            rollout_state=rollout_state,
            soak_seconds=args.soak_seconds,
            log_file=None,
        )
        return 0

    if not args.daemon:
        print(
            "Pass --daemon to run the background loop, or --status for soak clock only.\n"
            "Example:\n"
            "  export PROD_ADMIN_TOKEN=...\n"
            "  nohup .venv/bin/python scripts/gate10e_auto_rollout.py --daemon "
            "> artifacts/gate10e_auto_rollout.log 2>&1 &",
            file=sys.stderr,
        )
        return 2

    return daemon_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
