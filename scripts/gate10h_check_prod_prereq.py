#!/usr/bin/env python3
"""Gate 10H: production prerequisites before enabling neural.

Checks (repo-accurate surfaces — there is no /admin/latency):

- LLM/provider error rate from Prometheus ``llm_requests_total`` (< 5%)
- HTTP 5xx rate from ``http_requests_total`` (stable / < 5%)
- Latency p95 for ``/search`` and ``/recommendations`` from
  ``http_request_duration_seconds_bucket`` (≤ baseline × 1.10)

Optional admin snapshots: ``/admin/safety/status``, ``/admin/router-status``,
``/admin/router/metrics`` (context only; safety window is empty when kill/autotune OFF).

Usage:
  export PROD_ADMIN_TOKEN=...

  # Capture a latency/error baseline snapshot (do this once before neural):
  .venv/bin/python scripts/gate10h_check_prod_prereq.py --capture-baseline

  # Evaluate against that baseline:
  .venv/bin/python scripts/gate10h_check_prod_prereq.py \\
    --baseline artifacts/gate10h_prod_baseline.json --report

  # Sparse LLM series (post-10G traffic still low): allow WARN pass:
  .venv/bin/python scripts/gate10h_check_prod_prereq.py \\
    --baseline artifacts/gate10h_prod_baseline.json --allow-sparse-llm --report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_API = "https://dealhunter-production-api.onrender.com"
USER_AGENT = "SaveIQ-Gate10H-ProdPrereq/1.0"
DEFAULT_BASELINE = "artifacts/gate10h_prod_baseline.json"
DEFAULT_REPORT = "artifacts/gate10h_prod_prereq_report.json"

MAX_LLM_ERROR_RATE = 0.05
MAX_HTTP_5XX_RATE = 0.05
LATENCY_MULTIPLIER = 1.10
MIN_HTTP_SAMPLES = 50
MIN_LLM_SAMPLES = 20
LATENCY_PATHS = ("/search", "/recommendations")

BUCKET_RE = re.compile(
    r'^http_request_duration_seconds_bucket\{(?P<labels>[^}]*)\}\s+(?P<val>[0-9.eE+-]+)\s*$'
)
COUNTER_RE = re.compile(
    r'^(?P<name>http_requests_total|llm_requests_total)\{(?P<labels>[^}]*)\}\s+(?P<val>[0-9.eE+-]+)\s*$'
)
LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"')


class Gate10HPrereqError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def mark(ok: bool | None) -> str:
    if ok is True:
        return "PASS"
    if ok is False:
        return "FAIL"
    return "WARN"


def optional_prod_token() -> str | None:
    """PROD_ADMIN_TOKEN preferred; ADMIN_API_TOKEN only if not clearly staging-scoped."""
    token = os.environ.get("PROD_ADMIN_TOKEN", "").strip()
    if token:
        return token
    token = os.environ.get("ADMIN_API_TOKEN", "").strip()
    return token or None


def http_text(url: str, *, token: str | None = None, timeout: float = 60.0) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if token:
        headers["X-Admin-Token"] = token
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if exc.code == 401:
            hint = " (wrong/missing PROD_ADMIN_TOKEN / METRICS_TOKEN)"
        raise Gate10HPrereqError(f"GET {url} -> HTTP {exc.code}: {body[:400]}{hint}") from exc
    except Exception as exc:  # noqa: BLE001
        raise Gate10HPrereqError(f"GET {url} failed: {exc}") from exc


def http_json(url: str, *, token: str | None = None) -> dict[str, Any]:
    payload = http_text(url, token=token)
    data = json.loads(payload) if payload else {}
    if not isinstance(data, dict):
        raise Gate10HPrereqError(f"{url} did not return a JSON object")
    return data


def parse_labels(raw: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in LABEL_RE.finditer(raw)}


def parse_prometheus_snapshot(metrics: str) -> dict[str, Any]:
    http_total = 0.0
    http_5xx = 0.0
    llm_total = 0.0
    llm_errors = 0.0
    http_by_path: dict[str, float] = {p: 0.0 for p in LATENCY_PATHS}
    # path -> le -> cumulative count (prometheus buckets are cumulative)
    buckets: dict[str, dict[str, float]] = {p: {} for p in LATENCY_PATHS}

    for line in metrics.splitlines():
        if not line or line.startswith("#"):
            continue
        m = COUNTER_RE.match(line)
        if m:
            labels = parse_labels(m.group("labels"))
            val = float(m.group("val"))
            name = m.group("name")
            if name == "http_requests_total":
                http_total += val
                code = labels.get("status_code", "")
                if code.startswith("5"):
                    http_5xx += val
                path = labels.get("path")
                if path in http_by_path:
                    http_by_path[path] += val
            elif name == "llm_requests_total":
                llm_total += val
                if labels.get("result") == "error":
                    llm_errors += val
            continue

        m = BUCKET_RE.match(line)
        if not m:
            continue
        labels = parse_labels(m.group("labels"))
        path = labels.get("path")
        le = labels.get("le")
        if path not in buckets or le is None:
            continue
        buckets[path][le] = buckets[path].get(le, 0.0) + float(m.group("val"))

    latency_p95_ms: dict[str, float | None] = {}
    histogram_count: dict[str, float] = {}
    for path in LATENCY_PATHS:
        le_counts = buckets.get(path) or {}
        latency_p95_ms[path] = estimate_p95_ms(le_counts)
        histogram_count[path] = float(le_counts.get("+Inf") or 0.0)

    return {
        "http": {
            "total": http_total,
            "5xx": http_5xx,
            "error_rate": (http_5xx / http_total) if http_total else 0.0,
            "by_path": http_by_path,
        },
        "llm": {
            "total": llm_total,
            "errors": llm_errors,
            "error_rate": (llm_errors / llm_total) if llm_total else 0.0,
        },
        "latency_p95_ms": latency_p95_ms,
        "histogram_count": histogram_count,
    }


def estimate_p95_ms(le_counts: dict[str, float]) -> float | None:
    """Estimate histogram p95 (ms) from cumulative Prometheus buckets."""
    if not le_counts:
        return None
    finite: list[tuple[float, float]] = []
    total = 0.0
    for le, count in le_counts.items():
        if le == "+Inf":
            total = max(total, count)
            continue
        try:
            finite.append((float(le), count))
        except ValueError:
            continue
    if not finite:
        return None
    finite.sort(key=lambda x: x[0])
    if total <= 0:
        total = finite[-1][1]
    if total <= 0:
        return None
    target = 0.95 * total
    for upper, count in finite:
        if count >= target:
            return upper * 1000.0
    # Fell through finite buckets — use last finite upper bound.
    return finite[-1][0] * 1000.0


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Gate10HPrereqError(f"baseline file missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Gate10HPrereqError("baseline must be a JSON object")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate(
    snap: dict[str, Any],
    *,
    baseline: dict[str, Any] | None,
    max_llm_error_rate: float,
    max_http_5xx_rate: float,
    latency_multiplier: float,
    min_http_samples: int,
    min_llm_samples: int,
    allow_sparse_llm: bool,
    allow_sparse_latency: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    http = snap["http"]
    llm = snap["llm"]
    http_by_path = http.get("by_path") or {}
    hist_count = snap.get("histogram_count") or {}

    # HTTP 5xx
    http_ok: bool | None
    if http["total"] < min_http_samples:
        http_ok = None
        reason = f"insufficient http samples ({http['total']:.0f} < {min_http_samples})"
    else:
        http_ok = float(http["error_rate"]) < max_http_5xx_rate
        reason = (
            f"5xx_rate={http['error_rate']:.4f} "
            f"5xx={http['5xx']:.0f} total={http['total']:.0f} "
            f"threshold<{max_http_5xx_rate}"
        )
    checks.append({"name": "http_5xx", "ok": http_ok, "detail": reason})

    # LLM / provider errors
    llm_ok: bool | None
    if llm["total"] < min_llm_samples:
        if allow_sparse_llm:
            llm_ok = None
            reason = (
                f"sparse llm series ({llm['total']:.0f} < {min_llm_samples}); "
                "allowed via --allow-sparse-llm"
            )
        else:
            llm_ok = False
            reason = (
                f"insufficient llm samples ({llm['total']:.0f} < {min_llm_samples}); "
                "recheck later or pass --allow-sparse-llm with operator note"
            )
    else:
        llm_ok = float(llm["error_rate"]) < max_llm_error_rate
        reason = (
            f"llm_error_rate={llm['error_rate']:.4f} "
            f"errors={llm['errors']:.0f} total={llm['total']:.0f} "
            f"threshold<{max_llm_error_rate}"
        )
    checks.append({"name": "llm_provider_errors", "ok": llm_ok, "detail": reason})

    # Latency vs baseline
    if baseline is None:
        checks.append(
            {
                "name": "latency_p95_vs_baseline",
                "ok": False,
                "detail": "no --baseline provided (capture with --capture-baseline first)",
            }
        )
    else:
        base_lat = baseline.get("latency_p95_ms") or {}
        cur_lat = snap.get("latency_p95_ms") or {}
        for path in LATENCY_PATHS:
            base_ms = base_lat.get(path)
            cur_ms = cur_lat.get(path)
            path_hits = float(http_by_path.get(path) or 0.0)
            hist_hits = float(hist_count.get(path) or 0.0)
            if base_ms is None and cur_ms is None:
                detail = (
                    f"no histogram samples for {path} "
                    f"(http_total_path={path_hits:.0f} hist=+Inf:{hist_hits:.0f}); "
                    "warm with --warm-endpoints then re-capture baseline"
                )
                if allow_sparse_latency:
                    checks.append(
                        {
                            "name": f"latency_p95{path}",
                            "ok": None,
                            "detail": detail + "; allowed via --allow-sparse-latency",
                        }
                    )
                else:
                    checks.append(
                        {
                            "name": f"latency_p95{path}",
                            "ok": False,
                            "detail": detail,
                        }
                    )
                continue
            if base_ms is None or cur_ms is None:
                checks.append(
                    {
                        "name": f"latency_p95{path}",
                        "ok": False,
                        "detail": (
                            f"asymmetric p95 baseline={base_ms} current={cur_ms} "
                            f"(http_total_path={path_hits:.0f}); re-capture baseline "
                            "after --warm-endpoints"
                        ),
                    }
                )
                continue
            limit = float(base_ms) * latency_multiplier
            ok = float(cur_ms) <= limit
            checks.append(
                {
                    "name": f"latency_p95{path}",
                    "ok": ok,
                    "detail": (
                        f"p95_ms={float(cur_ms):.1f} baseline={float(base_ms):.1f} "
                        f"limit={limit:.1f} (×{latency_multiplier})"
                    ),
                }
            )

    # Fail only on explicit False; WARN (None) does not fail the gate.
    passed = all(c["ok"] is not False for c in checks)
    return passed, checks


def warm_endpoints(api_url: str, *, rounds: int = 3) -> None:
    """Generate a few /search + /recommendations observations for histograms."""
    import time

    for i in range(max(1, rounds)):
        try:
            http_text(f"{api_url}/search?q=buds&limit=5")
        except Gate10HPrereqError as exc:
            log(f"  warm /search failed: {exc}")
        try:
            body = json.dumps({"intent": "wireless earbuds under 50", "limit": 5}).encode(
                "utf-8"
            )
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(
                f"{api_url}/recommendations",
                headers=headers,
                method="POST",
                data=body,
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
            log(f"  warm /recommendations ok round={i + 1}")
        except urllib.error.HTTPError as exc:
            # 4xx still records latency buckets; only transport failure skips.
            log(f"  warm /recommendations HTTP {exc.code} round={i + 1} (latency still recorded)")
            try:
                exc.read()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log(f"  warm /recommendations failed: {exc}")
        time.sleep(0.2)


def capture_baseline(api_url: str, token: str | None, path: Path) -> dict[str, Any]:
    metrics_text = http_text(f"{api_url}/metrics", token=token)
    snap = parse_prometheus_snapshot(metrics_text)
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "api_url": api_url,
        "source": "prometheus_/metrics",
        "note": (
            "Process-lifetime cumulative counters/histograms. "
            "Use as Gate 10H pre-neural baseline; true pre-10G history is unavailable "
            "unless captured earlier."
        ),
        **snap,
    }
    save_json(path, payload)
    return payload


def run_check(args: argparse.Namespace) -> int:
    api_url = args.api_url.rstrip("/")
    token = optional_prod_token()
    repo = Path(__file__).resolve().parents[1]
    if not token:
        log(
            "WARN: PROD_ADMIN_TOKEN unset — /metrics may still work if METRICS_TOKEN "
            "is empty; admin safety/router checks will 401"
        )

    if args.warm_endpoints:
        log(f"warming latency endpoints rounds={args.warm_endpoints}")
        warm_endpoints(api_url, rounds=args.warm_endpoints)

    captured: dict[str, Any] | None = None
    if args.capture_baseline:
        out = Path(args.capture_baseline)
        if not out.is_absolute():
            out = repo / out
        captured = capture_baseline(api_url, token, out)
        log(f"baseline_written={out}")
        log(
            "  http_5xx_rate="
            f"{captured['http']['error_rate']:.4f} "
            f"llm_error_rate={captured['llm']['error_rate']:.4f} "
            f"search_p95_ms={captured['latency_p95_ms'].get('/search')} "
            f"recs_p95_ms={captured['latency_p95_ms'].get('/recommendations')} "
            f"http_by_path={captured['http'].get('by_path')}"
        )
        if not args.report and not args.baseline:
            return 0
        # Same-run evaluate can reuse the just-written baseline.
        if not args.baseline:
            args.baseline = str(args.capture_baseline)

    baseline: dict[str, Any] | None = captured
    if args.baseline and baseline is None:
        bpath = Path(args.baseline)
        if not bpath.is_absolute():
            bpath = repo / bpath
        baseline = load_baseline(bpath)
        log(f"baseline_loaded={bpath} captured_at={baseline.get('captured_at')}")
    elif args.baseline and captured is not None:
        log(f"baseline_loaded={args.baseline} captured_at={captured.get('captured_at')} (just written)")

    metrics_text = http_text(f"{api_url}/metrics", token=token)
    snap = parse_prometheus_snapshot(metrics_text)

    admin: dict[str, Any] = {}
    if token:
        try:
            safety = http_json(f"{api_url}/admin/safety/status", token=token)
            env = safety.get("env") or {}
            runtime = safety.get("runtime") or {}
            window = safety.get("window") or {}
            admin["safety"] = {
                "kill_env": env.get("feature_kill_switch"),
                "autotune_env": env.get("feature_auto_tuning"),
                "tripped": runtime.get("tripped"),
                "window_requests": window.get("requests"),
                "window_error_rate": window.get("error_rate"),
                "window_latency_p95_ms": window.get("latency_p95_ms"),
                "note": "window empty when kill/autotune OFF — Prometheus is source of truth",
            }
        except Gate10HPrereqError as exc:
            admin["safety_error"] = str(exc)

        try:
            router = http_json(f"{api_url}/admin/router-status", token=token)
            admin["router"] = {
                "active": router.get("active"),
                "mode": router.get("mode"),
                "chinese_providers_enabled": router.get("chinese_providers_enabled"),
                "live_ready": router.get("live_ready"),
            }
        except Gate10HPrereqError as exc:
            admin["router_error"] = str(exc)

        try:
            rmetrics = http_json(f"{api_url}/admin/router/metrics", token=token)
            admin["router_metrics"] = rmetrics
        except Gate10HPrereqError as exc:
            admin["router_metrics_error"] = str(exc)
    else:
        admin["skipped"] = "no PROD_ADMIN_TOKEN"

    passed, checks = evaluate(
        snap,
        baseline=baseline,
        max_llm_error_rate=args.max_llm_error_rate,
        max_http_5xx_rate=args.max_http_5xx_rate,
        latency_multiplier=args.latency_multiplier,
        min_http_samples=args.min_http_samples,
        min_llm_samples=args.min_llm_samples,
        allow_sparse_llm=args.allow_sparse_llm,
        allow_sparse_latency=args.allow_sparse_latency,
    )

    # Kill/autotune must stay OFF for Gate 10H prereq.
    safety_info = admin.get("safety") or {}
    if safety_info:
        kill_ok = (
            safety_info.get("kill_env") is not True
            and safety_info.get("autotune_env") is not True
            and safety_info.get("tripped") is not True
        )
        checks.append(
            {
                "name": "safety_kill_autotune_off",
                "ok": kill_ok,
                "detail": (
                    f"kill={safety_info.get('kill_env')} "
                    f"autotune={safety_info.get('autotune_env')} "
                    f"tripped={safety_info.get('tripped')}"
                ),
            }
        )
        passed = passed and kill_ok

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "api_url": api_url,
        "passed": passed,
        "snapshot": snap,
        "baseline_ref": {
            "path": args.baseline,
            "captured_at": (baseline or {}).get("captured_at"),
        },
        "checks": checks,
        "admin": admin,
        "thresholds": {
            "max_llm_error_rate": args.max_llm_error_rate,
            "max_http_5xx_rate": args.max_http_5xx_rate,
            "latency_multiplier": args.latency_multiplier,
            "min_http_samples": args.min_http_samples,
            "min_llm_samples": args.min_llm_samples,
            "allow_sparse_llm": args.allow_sparse_llm,
            "allow_sparse_latency": args.allow_sparse_latency,
        },
    }

    log("gate10h_prod_prereq=check")
    for item in checks:
        log(f"  {mark(item['ok'])} {item['name']}: {item['detail']}")
    log(f"gate10h_prod_prereq={'ok' if passed else 'error'}")

    if args.report:
        rpath = Path(args.report)
        if not rpath.is_absolute():
            rpath = repo / rpath
        save_json(rpath, report)
        log(f"report_written={rpath}")

    return 0 if passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gate 10H production prereq checks before enabling neural"
    )
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_API))
    parser.add_argument(
        "--baseline",
        default="",
        help=f"Baseline JSON from --capture-baseline (default compare path: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--capture-baseline",
        nargs="?",
        const=DEFAULT_BASELINE,
        default="",
        help=f"Write current Prometheus snapshot to PATH (default {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--report",
        nargs="?",
        const=DEFAULT_REPORT,
        default="",
        help=f"Write JSON report to PATH (default {DEFAULT_REPORT})",
    )
    parser.add_argument("--max-llm-error-rate", type=float, default=MAX_LLM_ERROR_RATE)
    parser.add_argument("--max-http-5xx-rate", type=float, default=MAX_HTTP_5XX_RATE)
    parser.add_argument("--latency-multiplier", type=float, default=LATENCY_MULTIPLIER)
    parser.add_argument("--min-http-samples", type=int, default=MIN_HTTP_SAMPLES)
    parser.add_argument("--min-llm-samples", type=int, default=MIN_LLM_SAMPLES)
    parser.add_argument(
        "--allow-sparse-llm",
        action="store_true",
        help="Treat insufficient llm_requests_total samples as WARN (not FAIL)",
    )
    parser.add_argument(
        "--allow-sparse-latency",
        action="store_true",
        help="Treat missing /search or /recommendations histogram p95 (no traffic) as WARN",
    )
    parser.add_argument(
        "--warm-endpoints",
        nargs="?",
        const=3,
        type=int,
        default=0,
        help="POST /recommendations + GET /search N times before capture/check (default N=3)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    # Convenience: if neither capture nor baseline, default baseline path when present.
    if not args.baseline and not args.capture_baseline:
        default_path = Path(__file__).resolve().parents[1] / DEFAULT_BASELINE
        if default_path.is_file():
            args.baseline = DEFAULT_BASELINE
            log(f"using_default_baseline={DEFAULT_BASELINE}")
    try:
        return run_check(args)
    except Gate10HPrereqError as exc:
        log(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
