#!/usr/bin/env python3
"""Gate 10F: flip global FEATURE_AI_ROUTER (mock only).

This repo controls production flags via `render-production.yaml` + Render Sync
(not a JSON config file). This script:

1. Verifies Gate 10E prerequisites (C4 soak clock, mock_router ready, canary 100%).
2. Sets FEATURE_AI_ROUTER=true and AI_ROUTER_MODE=mock in the production Blueprint.
3. Keeps FEATURE_KILL_SWITCH / FEATURE_AUTO_TUNING / live providers OFF.
4. Validates the Blueprint and updates rollout state + report.

Usage:
  # Check only
  .venv/bin/python scripts/gate10f_flip_router.py --check

  # Dry-run (show planned Blueprint edits)
  .venv/bin/python scripts/gate10f_flip_router.py --dry-run

  # Apply Blueprint edits locally (then commit / PR / Render Sync)
  export PROD_ADMIN_TOKEN=...
  .venv/bin/python scripts/gate10f_flip_router.py --apply

  # Skip live API checks (state-file only; not recommended)
  .venv/bin/python scripts/gate10f_flip_router.py --apply --skip-live-checks
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

DEFAULT_API = "https://dealhunter-production-api.onrender.com"
USER_AGENT = "SaveIQ-Gate10F-FlipRouter/1.0"
DEFAULT_SOAK = 24 * 60 * 60


class FlipError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def http_json(
    url: str,
    *,
    token: str | None = None,
    expected: int = 200,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["X-Admin-Token"] = token
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise FlipError(f"GET {url} -> HTTP {exc.code}: {body[:400]}") from exc
    except Exception as exc:  # noqa: BLE001
        raise FlipError(f"GET {url} failed: {exc}") from exc
    if status != expected:
        raise FlipError(f"GET {url} -> HTTP {status}: {payload[:400]}")
    data = json.loads(payload) if payload else {}
    if not isinstance(data, dict):
        raise FlipError(f"{url} did not return a JSON object")
    return data


def require_prod_token() -> str:
    token = (
        os.environ.get("PROD_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
    )
    if not token:
        raise FlipError(
            "PROD_ADMIN_TOKEN (or ADMIN_API_TOKEN) required for live prerequisite checks"
        )
    return token


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FlipError(f"missing state file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FlipError("state file must be a JSON object")
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def check_prerequisites(
    *,
    state: dict[str, Any],
    api_url: str,
    token: str | None,
    soak_seconds: int,
    skip_live: bool,
) -> list[str]:
    notes: list[str] = []

    if not state.get("staging_drill_passed_at"):
        raise FlipError("staging_drill not marked passed in state file")
    notes.append("staging_drill=pass")

    c4_at = state.get("c4_set_at")
    if not c4_at:
        raise FlipError("c4_set_at missing — run Gate 10E C4 first")
    elapsed = time.time() - float(c4_at)
    if elapsed < soak_seconds:
        raise FlipError(
            f"C4 soak incomplete: elapsed={fmt_duration(elapsed)} "
            f"need>={fmt_duration(soak_seconds)}"
        )
    notes.append(f"c4_soak=pass elapsed={fmt_duration(elapsed)}")

    if not state.get("mock_router_ready_at"):
        raise FlipError("mock_router_ready_at missing — run --phase mock_router first")
    notes.append("mock_router=pass")

    if int(state.get("c4_percentage") or 0) != 100:
        raise FlipError(
            f"state c4_percentage={state.get('c4_percentage')} (expected 100)"
        )

    if skip_live:
        notes.append("live_checks=skipped")
        return notes

    if not token:
        raise FlipError("live checks require PROD_ADMIN_TOKEN")

    canary = http_json(f"{api_url}/admin/canary/status", token=token)
    pct = int(canary.get("percentage") or -1)
    if not canary.get("enabled") or pct != 100:
        raise FlipError(
            f"live canary not at C4: enabled={canary.get('enabled')} percentage={pct}"
        )
    features = list(canary.get("features") or [])
    if "router" not in features:
        raise FlipError(f"canary features missing router: {features}")
    notes.append("live_canary=100%+router")

    safety = http_json(f"{api_url}/admin/safety/status", token=token)
    env = safety.get("env") or {}
    runtime = safety.get("runtime") or {}
    if env.get("feature_kill_switch") is True or env.get("feature_auto_tuning") is True:
        raise FlipError("production kill/autotune env must stay false during Gate 10F mock flip")
    if runtime.get("tripped") is True:
        raise FlipError(f"kill switch tripped: {runtime.get('trip_reason')}")
    notes.append("safety_env=off")

    router = http_json(f"{api_url}/admin/router-status", token=token)
    mode = str(router.get("mode") or "").lower()
    if mode == "live":
        raise FlipError("refusing flip while router mode is already live")
    notes.append(f"router_pre_mode={mode}")
    return notes


def blueprint_get(text: str, key: str) -> str | None:
    """Read env value for key; supports quoted or bare YAML scalars."""
    match = re.search(
        rf'(?m)^(\s+- key: {re.escape(key)}\n\s+value:\s*)(?:"([^"]*)"|([^\s#]+))',
        text,
    )
    if not match:
        return None
    return match.group(2) if match.group(2) is not None else match.group(3)


def blueprint_set(text: str, key: str, value: str) -> tuple[str, bool]:
    """Replace env value, preserving quote style of the existing line."""
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
        raise FlipError(f"failed to set {key} in Blueprint (matches={n})")
    return new_text, True


def apply_blueprint(path: Path, *, dry_run: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    before = {
        "FEATURE_AI_ROUTER": blueprint_get(text, "FEATURE_AI_ROUTER"),
        "AI_ROUTER_MODE": blueprint_get(text, "AI_ROUTER_MODE"),
        "FEATURE_KILL_SWITCH": blueprint_get(text, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text, "FEATURE_AUTO_TUNING"),
        "FEATURE_CHINESE_LLM_PROVIDERS": blueprint_get(
            text, "FEATURE_CHINESE_LLM_PROVIDERS"
        ),
    }
    planned = {
        "FEATURE_AI_ROUTER": "true",
        "AI_ROUTER_MODE": "mock",
        "FEATURE_KILL_SWITCH": "false",
        "FEATURE_AUTO_TUNING": "false",
    }
    # Never touch Chinese / live keys here.
    text2 = text
    for key, value in planned.items():
        text2, _ = blueprint_set(text2, key, value)

    after = {
        "FEATURE_AI_ROUTER": blueprint_get(text2, "FEATURE_AI_ROUTER"),
        "AI_ROUTER_MODE": blueprint_get(text2, "AI_ROUTER_MODE"),
        "FEATURE_KILL_SWITCH": blueprint_get(text2, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text2, "FEATURE_AUTO_TUNING"),
        "FEATURE_CHINESE_LLM_PROVIDERS": blueprint_get(
            text2, "FEATURE_CHINESE_LLM_PROVIDERS"
        ),
    }
    if after["FEATURE_CHINESE_LLM_PROVIDERS"] not in {None, "false"}:
        raise FlipError("refusing to proceed while FEATURE_CHINESE_LLM_PROVIDERS is enabled")

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


def validate_blueprint(repo: Path, python: str) -> None:
    cmd = [
        python,
        str(repo / "scripts" / "validate_render_blueprint.py"),
        "render-production.yaml",
        "--profile",
        "production",
    ]
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        raise FlipError("Blueprint validation failed")


def update_report(path: Path, *, result: dict[str, Any], notes: list[str]) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    section = f"""

## Gate 10F — global AI router flip (mock)

| Field | Value |
| --- | --- |
| Timestamp (UTC) | {stamp} |
| FEATURE_AI_ROUTER | `{result['after'].get('FEATURE_AI_ROUTER')}` |
| AI_ROUTER_MODE | `{result['after'].get('AI_ROUTER_MODE')}` |
| FEATURE_KILL_SWITCH | `{result['after'].get('FEATURE_KILL_SWITCH')}` |
| FEATURE_AUTO_TUNING | `{result['after'].get('FEATURE_AUTO_TUNING')}` |
| Dry-run | {result.get('dry_run')} |
| Prerequisites | {", ".join(notes)} |

**Next ops:** commit Blueprint → PR → merge → Render Sync `saveiq-production` →  
`production_smoke.py --allow-active-canary --require-admin` → confirm `/admin/router-status` mode=mock.

Live providers remain **disabled** until a separate Gate 10F live checklist.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        content = path.read_text(encoding="utf-8")
        content = content.replace(
            "| Global `FEATURE_AI_ROUTER` env flip | **NOT DONE** | Optional later + Render Sync |",
            "| Global `FEATURE_AI_ROUTER` env flip | **BLUEPRINT UPDATED** | `true` + `mode=mock`; awaiting Render Sync |",
        )
        content = content.replace(
            "- AI router global status: `active=False mode=disabled` (effective mock via canary for all traffic)",
            "- AI router global status: Blueprint `FEATURE_AI_ROUTER=true` + `AI_ROUTER_MODE=mock` (awaiting Render Sync)",
        )
        if "## Gate 10F — global AI router flip" in content:
            head, _, _ = content.partition("## Gate 10F — global AI router flip")
            content = head.rstrip() + section
        else:
            content = content.rstrip() + section
    else:
        content = "# Gate 10E / 10F Rollout Report\n" + section
    path.write_text(content + "\n", encoding="utf-8")
    log(f"report_updated={path}")


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10F flip FEATURE_AI_ROUTER (mock)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Verify prerequisites only")
    mode.add_argument("--dry-run", action="store_true", help="Show Blueprint edits; no write")
    mode.add_argument("--apply", action="store_true", help="Write render-production.yaml")
    parser.add_argument("--force", action="store_true", help="Skip prerequisite checks (dangerous)")
    parser.add_argument("--skip-live-checks", action="store_true")
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_API))
    parser.add_argument(
        "--soak-seconds",
        type=int,
        default=int(os.environ.get("GATE10E_SOAK_SECONDS", str(DEFAULT_SOAK))),
    )
    parser.add_argument(
        "--state-file",
        default=str(repo / "artifacts" / "gate10e_rollout_state.json"),
    )
    parser.add_argument(
        "--blueprint",
        default=str(repo / "render-production.yaml"),
    )
    parser.add_argument(
        "--report-file",
        default=str(repo / "docs" / "GATE_10E_ROLLOUT_REPORT.md"),
    )
    parser.add_argument("--repo-root", default=str(repo))
    parser.add_argument("--python", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root)
    python = args.python or os.environ.get("PYTHON") or str(repo / ".venv" / "bin" / "python")
    if not Path(python).exists():
        python = sys.executable

    state_path = Path(args.state_file)
    blueprint_path = Path(args.blueprint)
    report_path = Path(args.report_file)

    log("gate10f_flip=start")
    try:
        state = load_state(state_path)
        notes: list[str] = []
        if args.force:
            log("WARNING: --force skips prerequisite checks")
            notes.append("force=true")
        else:
            token = None
            if not args.skip_live_checks:
                token = require_prod_token()
            notes = check_prerequisites(
                state=state,
                api_url=args.api_url.rstrip("/"),
                token=token,
                soak_seconds=args.soak_seconds,
                skip_live=args.skip_live_checks,
            )
            for note in notes:
                log(f"prereq_ok {note}")

        if args.check:
            log("gate10f_flip=ok check_only")
            return 0

        result = apply_blueprint(blueprint_path, dry_run=not args.apply)
        if args.apply:
            validate_blueprint(repo, python)
            state["gate10f_router_flip"] = {
                "status": "blueprint_updated",
                "timestamp": time.time(),
                "iso": datetime.now(timezone.utc).isoformat(),
                "FEATURE_AI_ROUTER": "true",
                "AI_ROUTER_MODE": "mock",
                "FEATURE_KILL_SWITCH": "false",
                "FEATURE_AUTO_TUNING": "false",
                "awaiting_render_sync": True,
            }
            history = list(state.get("history") or [])
            history.append(
                {
                    "ts": time.time(),
                    "event": "gate10f_router_flip_blueprint",
                    "mode": "mock",
                }
            )
            state["history"] = history[-200:]
            save_state(state_path, state)
            update_report(report_path, result=result, notes=notes)
            log("ACTION_REQUIRED:")
            log("  1) Review git diff render-production.yaml")
            log("  2) Commit + PR + merge")
            log("  3) Render → saveiq-production → Sync")
            log("  4) ADMIN_API_TOKEN=... .venv/bin/python scripts/production_smoke.py \\")
            log("       --allow-active-canary --require-admin")
            log("  5) Confirm GET /admin/router-status → active + mode=mock (not live)")
            log("gate10f_flip=ok apply_local (awaiting Render Sync)")
        else:
            log("gate10f_flip=ok dry_run (Blueprint not written; report unchanged)")
        return 0
    except FlipError as exc:
        log(f"gate10f_flip=error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
