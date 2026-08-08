#!/usr/bin/env python3
"""Lightweight Gate 10E canary soak monitor (public metrics; optional admin).

Writes JSON lines to artifacts/gate10e_soak_monitor.jsonl
Exit 0 = healthy, 2 = breach (caller may rollback).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_API = "https://dealhunter-production-api.onrender.com"
USER_AGENT = "SaveIQ-Gate10E-SoakMonitor/1.0"


def http_get(
    url: str, *, token: str | None = None, timeout: float = 60.0
) -> tuple[int, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if token:
        headers["X-Admin-Token"] = token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body


def parse_http_counters(metrics: str) -> dict[str, Any]:
    total = 0.0
    five = 0.0
    by_canary: dict[str, float] = {}
    by_canary_5xx: dict[str, float] = {}
    for line in metrics.splitlines():
        if not line.startswith("http_requests_total{"):
            continue
        m = re.search(
            r'canary="(?P<canary>[^"]+)".*status_code="(?P<code>\d+)".*\s(?P<val>[0-9.eE+-]+)$',
            line,
        )
        if not m:
            continue
        canary = m.group("canary")
        code = m.group("code")
        val = float(m.group("val"))
        total += val
        by_canary[canary] = by_canary.get(canary, 0.0) + val
        if code.startswith("5"):
            five += val
            by_canary_5xx[canary] = by_canary_5xx.get(canary, 0.0) + val
    err_rate = (five / total) if total else 0.0
    return {
        "http_total": total,
        "http_5xx": five,
        "error_rate": err_rate,
        "by_canary": by_canary,
        "by_canary_5xx": by_canary_5xx,
    }


def soak_remaining(
    state_path: Path, *, phase: str, soak_seconds: int = 86400
) -> dict[str, Any]:
    if not state_path.is_file():
        return {"ok": False, "error": "missing_state"}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    key = "c3_set_at" if phase == "c3" else "c4_set_at"
    started = state.get(key)
    if not started:
        return {"ok": False, "error": f"{key}_missing", "state": state}
    started_f = float(started)
    now = time.time()
    left = max(0.0, soak_seconds - (now - started_f))
    return {
        "ok": True,
        "phase": phase,
        "started_at": started_f,
        "elapsed_s": now - started_f,
        "remaining_s": left,
        "complete": left <= 0,
        "percentage": state.get("c3_percentage" if phase == "c3" else "c4_percentage"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_API))
    parser.add_argument(
        "--state-file",
        default=str(
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "gate10e_rollout_state.json"
        ),
    )
    parser.add_argument("--phase", choices=("c3", "c4"), default="c3")
    parser.add_argument("--log-file", default="")
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=0.05,
        help="Absolute process error-rate threshold for alert (cumulative counters)",
    )
    args = parser.parse_args()
    api = args.api_url.rstrip("/")
    token = (
        os.environ.get("PROD_ADMIN_TOKEN", "").strip()
        or os.environ.get("ADMIN_API_TOKEN", "").strip()
        or None
    )
    now = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "ts": now,
        "phase": args.phase,
        "breach": False,
        "notes": [],
    }

    code, health_body = http_get(f"{api}/health")
    record["health_status"] = code
    healthy = code == 200 and '"status":"ok"' in health_body.replace(" ", "")
    if not healthy:
        # tolerate compact JSON
        healthy = code == 200 and '"ok"' in health_body
    record["healthy"] = healthy
    if not healthy:
        record["breach"] = True
        record["notes"].append(f"health_failed status={code} body={health_body[:200]}")

    code, metrics = http_get(f"{api}/metrics")
    record["metrics_status"] = code
    if code != 200:
        record["breach"] = True
        record["notes"].append(f"metrics_failed status={code}")
    else:
        counters = parse_http_counters(metrics)
        record["counters"] = counters
        # Cumulative counters can be noisy after long uptime; only flag if sample is large
        # and absolute error rate is extreme (indicates active incident).
        if (
            counters["http_total"] >= 50
            and counters["error_rate"] >= args.max_error_rate
        ):
            record["breach"] = True
            record["notes"].append(
                f"error_rate={counters['error_rate']:.4f} >= {args.max_error_rate}"
            )

    soak = soak_remaining(Path(args.state_file), phase=args.phase)
    record["soak"] = soak

    if token:
        code, body = http_get(f"{api}/admin/canary/status", token=token)
        if code == 200:
            try:
                canary = json.loads(body)
            except json.JSONDecodeError:
                canary = {"_raw": body[:300]}
            record["canary"] = canary
            expected = 25 if args.phase == "c3" else 100
            pct = int(canary.get("percentage") or -1)
            if not canary.get("enabled") or pct != expected:
                record["breach"] = True
                record["notes"].append(
                    f"unexpected_canary enabled={canary.get('enabled')} pct={pct} expected={expected}"
                )
        code, body = http_get(f"{api}/admin/safety/status", token=token)
        if code == 200:
            try:
                safety = json.loads(body)
            except json.JSONDecodeError:
                safety = {}
            env = safety.get("env") or {}
            runtime = safety.get("runtime") or {}
            record["safety"] = {
                "kill_env": env.get("feature_kill_switch"),
                "tune_env": env.get("feature_auto_tuning"),
                "tripped": runtime.get("tripped"),
            }
            if env.get("feature_kill_switch") or env.get("feature_auto_tuning"):
                record["breach"] = True
                record["notes"].append("prod_safety_env_unexpectedly_on")
            if runtime.get("tripped"):
                record["breach"] = True
                record["notes"].append("kill_tripped")
    else:
        record["notes"].append("admin_skipped_no_token")

    log_path = Path(
        args.log_file
        or (
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "gate10e_soak_monitor.jsonl"
        )
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")

    print(json.dumps(record, indent=2, sort_keys=True))
    if record["breach"]:
        print("soak_monitor=BREACH", file=sys.stderr)
        return 2
    print("soak_monitor=ok")
    if soak.get("complete"):
        print("soak_complete=yes")
    else:
        rem = float(soak.get("remaining_s") or 0)
        print(f"soak_remaining_h={rem / 3600:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
