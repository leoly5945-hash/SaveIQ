#!/usr/bin/env python3
"""Gate 10G: evaluate and enable live AI providers (Chinese LLM).

Production flags live in `render-production.yaml` + Render Sync (not JSON config).

Phases:
  --check     Gate 10E/10F prerequisites (state + live API)
  --evaluate  Readiness report (keys present, checklist, risk notes) — no Blueprint write
  --dry-run   Show planned Blueprint edits for live + Chinese
  --apply     Write Blueprint (requires explicit confirm flags)

Safety:
  - Keeps FEATURE_KILL_SWITCH / FEATURE_AUTO_TUNING = false
  - Does not write API keys (Render secrets stay sync:false)
  - --apply requires --confirm-live --confirm-chinese plus operator acks
  - After apply: commit → PR → merge → Render Sync → smoke with
    --allow-active-canary --allow-live-router --allow-chinese-providers

Usage:
  export PROD_ADMIN_TOKEN=...
  .venv/bin/python scripts/gate10g_live_providers.py --check
  .venv/bin/python scripts/gate10g_live_providers.py --evaluate
  .venv/bin/python scripts/gate10g_live_providers.py --dry-run
  .venv/bin/python scripts/gate10g_live_providers.py --apply \\
    --confirm-live --confirm-chinese \\
    --ack-tos --ack-pii --ack-cost-budget --ack-keys-in-render
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
USER_AGENT = "SaveIQ-Gate10G-LiveProviders/1.0"
DEFAULT_SOAK = 24 * 60 * 60
CHINESE_KEY_NAMES = ("deepseek", "dashscope", "baidu")


class Gate10GError(RuntimeError):
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
        raise Gate10GError(f"GET {url} -> HTTP {exc.code}: {body[:400]}") from exc
    except Exception as exc:  # noqa: BLE001
        raise Gate10GError(f"GET {url} failed: {exc}") from exc
    if status != expected:
        raise Gate10GError(f"GET {url} -> HTTP {status}: {payload[:400]}")
    data = json.loads(payload) if payload else {}
    if not isinstance(data, dict):
        raise Gate10GError(f"{url} did not return a JSON object")
    return data


def require_prod_token() -> str:
    token = (
        os.environ.get("PROD_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
    )
    if not token:
        raise Gate10GError(
            "PROD_ADMIN_TOKEN (or ADMIN_API_TOKEN) required for live checks/evaluate"
        )
    return token


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Gate10GError(f"missing state file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Gate10GError("state file must be a JSON object")
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


def mark(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def check_prerequisites(
    *,
    state: dict[str, Any],
    api_url: str,
    token: str | None,
    soak_seconds: int,
    skip_live: bool,
) -> tuple[dict[str, bool], list[str]]:
    """Return (checks, notes). Raises if hard failures when not skip_live."""
    checks: dict[str, bool] = {
        "gate_10e_complete": False,
        "gate_10f_complete": False,
        "canary_100": False,
        "kill_switch_off": False,
        "auto_tune_off": False,
        "mock_router_ok": False,
    }
    notes: list[str] = []

    # Gate 10E — real state keys (not soak_c4.status)
    has_drill = bool(state.get("staging_drill_passed_at"))
    has_c4 = int(state.get("c4_percentage") or 0) == 100 and bool(state.get("c4_set_at"))
    c4_elapsed = (
        time.time() - float(state["c4_set_at"]) if state.get("c4_set_at") else 0.0
    )
    soak_ok = bool(state.get("c4_set_at")) and c4_elapsed >= soak_seconds
    mock_ok = bool(state.get("mock_router_ready_at"))
    checks["gate_10e_complete"] = has_drill and has_c4 and soak_ok and mock_ok
    checks["mock_router_ok"] = mock_ok
    notes.append(
        f"10e drill={has_drill} c4=100={has_c4} "
        f"soak={fmt_duration(c4_elapsed)}>={fmt_duration(soak_seconds)} mock={mock_ok}"
    )

    # Gate 10F — blueprint flip recorded (live verify below)
    flip = state.get("gate10f_router_flip") or state.get("router_flip") or {}
    flip_recorded = bool(flip) and str(flip.get("FEATURE_AI_ROUTER", "")).lower() in {
        "true",
        "1",
        "done",
    }
    # Also accept status from flip script
    if flip.get("status") in {"DONE", "blueprint_updated", "synced", "verified"}:
        flip_recorded = True
    checks["gate_10f_complete"] = flip_recorded
    notes.append(f"10f_state_flip={flip_recorded} status={flip.get('status')}")

    if skip_live:
        # Without live API, canary/safety checks stay false unless forced later.
        notes.append("live_checks=skipped")
        for key, ok in checks.items():
            log(f"  {key}: {mark(ok)}")
        return checks, notes

    if not token:
        raise Gate10GError("live checks require PROD_ADMIN_TOKEN")

    canary = http_json(f"{api_url}/admin/canary/status", token=token)
    pct = int(canary.get("percentage") or -1)
    canary_ok = bool(canary.get("enabled")) and pct == 100
    checks["canary_100"] = canary_ok
    notes.append(f"live_canary enabled={canary.get('enabled')} percentage={pct}")

    safety = http_json(f"{api_url}/admin/safety/status", token=token)
    env = safety.get("env") or {}
    runtime = safety.get("runtime") or {}
    kill_off = env.get("feature_kill_switch") is not True
    autotune_off = env.get("feature_auto_tuning") is not True
    checks["kill_switch_off"] = kill_off
    checks["auto_tune_off"] = autotune_off
    if runtime.get("tripped") is True:
        raise Gate10GError(f"kill switch tripped: {runtime.get('trip_reason')}")
    notes.append("safety_env=off")

    router = http_json(f"{api_url}/admin/router-status", token=token)
    mode = str(router.get("mode") or "").lower()
    active = router.get("active") is True
    # 10F verified posture: global mock ON. If already live, evaluate may continue
    # but apply should refuse unless --force.
    if active and mode == "mock":
        checks["gate_10f_complete"] = True
        notes.append("live_router=active+mock (10F verified)")
    elif active and mode == "live":
        checks["gate_10f_complete"] = True
        notes.append("live_router=already_live")
    else:
        notes.append(f"live_router=active={router.get('active')} mode={mode}")

    for key, ok in checks.items():
        log(f"  {key}: {mark(ok)}")
    return checks, notes


def evaluate_readiness(
    *,
    api_url: str,
    token: str,
    out_path: Path,
    checks: dict[str, bool],
    notes: list[str],
) -> dict[str, Any]:
    router = http_json(f"{api_url}/admin/router-status", token=token)
    models = http_json(f"{api_url}/admin/models/status", token=token)
    keys = dict(models.get("keys_present") or {})
    chinese_keys = {name: bool(keys.get(name)) for name in CHINESE_KEY_NAMES}
    any_chinese_key = any(chinese_keys.values())
    western_keys = {
        "openai": bool(keys.get("openai")),
        "anthropic": bool(keys.get("anthropic")),
    }

    blockers: list[str] = []
    for name, ok in checks.items():
        if not ok:
            blockers.append(f"prerequisite:{name}")
    if not any_chinese_key:
        blockers.append(
            "no Chinese provider keys present in Render "
            "(need DEEPSEEK_API_KEY and/or DASHSCOPE_API_KEY and/or BAIDU_* )"
        )
    if str(router.get("mode") or "").lower() == "live" and router.get("active"):
        # Already live — evaluate only.
        pass

    checklist = {
        "partner_tos_reviewed": False,
        "pii_policy_ok": False,
        "cost_budget_set": False,
        "provider_keys_in_render": any_chinese_key,
        "canary_rollback_drill_done": checks.get("gate_10e_complete", False),
        "gate_10f_mock_verified": checks.get("gate_10f_complete", False),
    }

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready_for_apply": not blockers and all(checks.values()) and any_chinese_key,
        "blockers": blockers,
        "prerequisites": checks,
        "notes": notes,
        "router": {
            "active": router.get("active"),
            "mode": router.get("mode"),
            "live_ready": router.get("live_ready"),
            "chinese_providers_enabled": router.get("chinese_providers_enabled"),
            "providers_configured": router.get("providers_configured"),
        },
        "models_status": {
            "chinese_providers_enabled": models.get("chinese_providers_enabled"),
            "router_mode": models.get("router_mode"),
            "keys_present": keys,
            "chinese_keys": chinese_keys,
            "western_keys": western_keys,
        },
        "operator_checklist": checklist,
        "planned_blueprint": {
            "FEATURE_AI_ROUTER": "true",
            "AI_ROUTER_MODE": "live",
            "FEATURE_CHINESE_LLM_PROVIDERS": "true",
            "FEATURE_KILL_SWITCH": "false",
            "FEATURE_AUTO_TUNING": "false",
        },
        "risks": [
            "Live LLM calls can spike cost within hours without budgets/rate limits",
            "Chinese providers require keys in Render (sync:false) before traffic works",
            "Rollback: set AI_ROUTER_MODE=mock and FEATURE_CHINESE_LLM_PROVIDERS=false, Sync",
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log(f"evaluation_written={out_path}")
    log(f"ready_for_apply={report['ready_for_apply']}")
    if blockers:
        for item in blockers:
            log(f"blocker: {item}")
    else:
        log("blockers=none")
    log(
        "chinese_keys "
        + json.dumps(chinese_keys, sort_keys=True)
        + f" any={any_chinese_key}"
    )
    log(
        "router "
        f"active={router.get('active')} mode={router.get('mode')} "
        f"chinese_enabled={router.get('chinese_providers_enabled')} "
        f"live_ready={router.get('live_ready')}"
    )
    return report


def blueprint_get(text: str, key: str) -> str | None:
    match = re.search(
        rf'(?m)^(\s+- key: {re.escape(key)}\n\s+value:\s*)(?:"([^"]*)"|([^\s#]+))',
        text,
    )
    if not match:
        return None
    return match.group(2) if match.group(2) is not None else match.group(3)


def blueprint_set(text: str, key: str, value: str) -> tuple[str, bool]:
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
        raise Gate10GError(f"failed to set {key} in Blueprint (matches={n})")
    return new_text, True


def apply_blueprint(path: Path, *, dry_run: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    before = {
        "FEATURE_AI_ROUTER": blueprint_get(text, "FEATURE_AI_ROUTER"),
        "AI_ROUTER_MODE": blueprint_get(text, "AI_ROUTER_MODE"),
        "FEATURE_CHINESE_LLM_PROVIDERS": blueprint_get(
            text, "FEATURE_CHINESE_LLM_PROVIDERS"
        ),
        "FEATURE_KILL_SWITCH": blueprint_get(text, "FEATURE_KILL_SWITCH"),
        "FEATURE_AUTO_TUNING": blueprint_get(text, "FEATURE_AUTO_TUNING"),
    }
    planned = {
        "FEATURE_AI_ROUTER": "true",
        "AI_ROUTER_MODE": "live",
        "FEATURE_CHINESE_LLM_PROVIDERS": "true",
        "FEATURE_KILL_SWITCH": "false",
        "FEATURE_AUTO_TUNING": "false",
    }
    text2 = text
    for key, value in planned.items():
        text2, _ = blueprint_set(text2, key, value)

    after = {key: blueprint_get(text2, key) for key in before}
    if after["FEATURE_KILL_SWITCH"] != "false" or after["FEATURE_AUTO_TUNING"] != "false":
        raise Gate10GError("refusing apply while kill/autotune would not stay false")

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
        "--allow-live-ai",
    ]
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(repo), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        raise Gate10GError("Blueprint validation failed")


def update_report(path: Path, *, result: dict[str, Any], notes: list[str]) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    section = f"""

## Gate 10G — live providers / Chinese LLM

| Field | Value |
| --- | --- |
| Timestamp (UTC) | {stamp} |
| FEATURE_AI_ROUTER | `{result['after'].get('FEATURE_AI_ROUTER')}` |
| AI_ROUTER_MODE | `{result['after'].get('AI_ROUTER_MODE')}` |
| FEATURE_CHINESE_LLM_PROVIDERS | `{result['after'].get('FEATURE_CHINESE_LLM_PROVIDERS')}` |
| FEATURE_KILL_SWITCH | `{result['after'].get('FEATURE_KILL_SWITCH')}` |
| FEATURE_AUTO_TUNING | `{result['after'].get('FEATURE_AUTO_TUNING')}` |
| Dry-run | {result.get('dry_run')} |
| Prerequisites | {", ".join(notes)} |

**Next ops:** commit Blueprint → PR → merge → Render Sync →  
`production_smoke.py --allow-active-canary --allow-live-router --allow-chinese-providers --require-admin`  
Confirm `/admin/router-status` mode=live + chinese enabled; keys_present for at least one Chinese provider.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        content = path.read_text(encoding="utf-8")
        if "## Gate 10G — live providers" in content:
            head, _, _ = content.partition("## Gate 10G — live providers")
            content = head.rstrip() + section
        else:
            content = content.rstrip() + section
    else:
        content = "# Gate 10E / 10F / 10G Rollout Report\n" + section
    path.write_text(content + "\n", encoding="utf-8")
    log(f"report_updated={path}")


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Gate 10G evaluate/enable live + Chinese LLM providers"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Verify prerequisites only")
    mode.add_argument(
        "--evaluate",
        action="store_true",
        help="Prerequisites + readiness report (keys/checklist); no Blueprint write",
    )
    mode.add_argument("--dry-run", action="store_true", help="Show Blueprint edits; no write")
    mode.add_argument("--apply", action="store_true", help="Write render-production.yaml")
    parser.add_argument("--force", action="store_true", help="Skip prerequisite failures")
    parser.add_argument("--skip-live-checks", action="store_true")
    parser.add_argument("--confirm-live", action="store_true", help="Required for --apply")
    parser.add_argument("--confirm-chinese", action="store_true", help="Required for --apply")
    parser.add_argument("--ack-tos", action="store_true", help="Required for --apply")
    parser.add_argument("--ack-pii", action="store_true", help="Required for --apply")
    parser.add_argument("--ack-cost-budget", action="store_true", help="Required for --apply")
    parser.add_argument(
        "--ack-keys-in-render",
        action="store_true",
        help="Required for --apply (operator asserts keys set in Render)",
    )
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
        "--eval-out",
        default=str(repo / "artifacts" / "gate10g_evaluation.json"),
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


def require_apply_confirms(args: argparse.Namespace) -> None:
    missing = []
    for flag in (
        "confirm_live",
        "confirm_chinese",
        "ack_tos",
        "ack_pii",
        "ack_cost_budget",
        "ack_keys_in_render",
    ):
        if not getattr(args, flag):
            missing.append(f"--{flag.replace('_', '-')}")
    if missing:
        raise Gate10GError(
            "refusing --apply without confirmations: " + ", ".join(missing)
        )


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root)
    python = args.python or os.environ.get("PYTHON") or str(repo / ".venv" / "bin" / "python")
    if not Path(python).exists():
        python = sys.executable

    state_path = Path(args.state_file)
    blueprint_path = Path(args.blueprint)
    report_path = Path(args.report_file)
    eval_path = Path(args.eval_out)

    log("gate10g_live=start")
    try:
        state = load_state(state_path)
        notes: list[str] = []
        checks: dict[str, bool] = {}

        token = None
        if not args.skip_live_checks:
            token = require_prod_token()

        if args.force:
            log("WARNING: --force skips prerequisite enforcement")
            notes.append("force=true")
            checks, notes2 = check_prerequisites(
                state=state,
                api_url=args.api_url.rstrip("/"),
                token=token,
                soak_seconds=args.soak_seconds,
                skip_live=args.skip_live_checks,
            )
            notes.extend(notes2)
        else:
            checks, notes = check_prerequisites(
                state=state,
                api_url=args.api_url.rstrip("/"),
                token=token,
                soak_seconds=args.soak_seconds,
                skip_live=args.skip_live_checks,
            )
            if not all(checks.values()):
                failed = [k for k, v in checks.items() if not v]
                raise Gate10GError(f"prerequisites failed: {', '.join(failed)}")

        if args.check:
            log("gate10g_live=ok check_only")
            return 0

        if args.evaluate or args.dry_run or args.apply:
            if args.skip_live_checks and args.evaluate:
                raise Gate10GError("--evaluate requires live API (omit --skip-live-checks)")
            if args.evaluate or (args.apply and not args.skip_live_checks):
                if not token:
                    token = require_prod_token()
                report = evaluate_readiness(
                    api_url=args.api_url.rstrip("/"),
                    token=token,
                    out_path=eval_path,
                    checks=checks,
                    notes=notes,
                )
                if args.evaluate:
                    log("gate10g_live=ok evaluate")
                    return 0 if report.get("ready_for_apply") else 2
                if args.apply and not args.force and not report.get("ready_for_apply"):
                    raise Gate10GError(
                        "evaluation not ready_for_apply; fix blockers or use --force"
                    )

        if args.apply:
            require_apply_confirms(args)
            if args.skip_live_checks:
                if not args.force:
                    raise Gate10GError(
                        "--apply --skip-live-checks requires --force "
                        "(prefer live --apply after --evaluate)"
                    )
                if not eval_path.is_file():
                    raise Gate10GError("missing evaluation file; run --evaluate first")
                eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
                if not eval_data.get("ready_for_apply"):
                    raise Gate10GError(
                        "prior evaluation not ready_for_apply; re-run --evaluate"
                    )
                log("WARNING: apply with --force --skip-live-checks (using prior evaluation)")
                notes.append("apply_skip_live=true")

        if args.dry_run or args.apply:
            result = apply_blueprint(blueprint_path, dry_run=not args.apply)
            if args.apply:
                validate_blueprint(repo, python)
                state["gate10g_live_providers"] = {
                    "status": "blueprint_updated",
                    "timestamp": time.time(),
                    "iso": datetime.now(timezone.utc).isoformat(),
                    "FEATURE_AI_ROUTER": "true",
                    "AI_ROUTER_MODE": "live",
                    "FEATURE_CHINESE_LLM_PROVIDERS": "true",
                    "FEATURE_KILL_SWITCH": "false",
                    "FEATURE_AUTO_TUNING": "false",
                    "awaiting_render_sync": True,
                }
                history = list(state.get("history") or [])
                history.append(
                    {
                        "ts": time.time(),
                        "event": "gate10g_live_providers_blueprint",
                        "mode": "live",
                        "chinese": True,
                    }
                )
                state["history"] = history[-200:]
                save_state(state_path, state)
                update_report(report_path, result=result, notes=notes)
                log("ACTION_REQUIRED:")
                log("  1) Ensure Chinese provider keys are set in Render (sync:false)")
                log("  2) Review git diff render-production.yaml")
                log("  3) Commit + PR + merge")
                log("  4) Render → saveiq-production → Sync")
                log("  5) ADMIN_API_TOKEN=... .venv/bin/python scripts/production_smoke.py \\")
                log(
                    "       --allow-active-canary --allow-live-router "
                    "--allow-chinese-providers --require-admin"
                )
                log("  6) Confirm GET /admin/router-status → mode=live + chinese enabled")
                log("gate10g_live=ok apply_local (awaiting Render Sync)")
            else:
                log("gate10g_live=ok dry_run (Blueprint not written)")
            return 0

        raise Gate10GError("no action selected")
    except Gate10GError as exc:
        log(f"gate10g_live=error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
