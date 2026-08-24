#!/usr/bin/env python3
"""Gate 10H: production neural soak monitor.

Polls live prod surfaces during n10/n25/n50/n100 soak and writes JSONL + a
summary report. Does **not** mutate canary, flags, or policy.

Surfaces:
  GET /admin/bandit/status
  GET /metrics  (Prometheus: HTTP 5xx, latency histograms, cache_events_total)
  GET /admin/router/metrics
  GET /admin/safety/status (kill/autotune must stay OFF)

Thresholds (defaults):
  - HTTP 5xx delta == 0; HTTP error rate < 0.1%
  - LLM/provider error rate < 0.1% (Prometheus llm_requests_total + /admin/router/metrics)
  - /search and /recommendations p95 ≤ baseline × 1.10
  - Cache hit rate > 60% (WARN if no cache samples)
  - neural.ready: WARN by default (live soak still sample_count=0); FAIL with --require-neural-ready

Alerts (optional env):
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  SOAK_ALERT_WEBHOOK_URL  (POST JSON)
  SMTP_HOST + SMTP_TO     (plain email)

Usage:
  export PROD_ADMIN_TOKEN=...

  .venv/bin/python scripts/gate10h_monitor_soak.py --phase n50 --status
  .venv/bin/python scripts/gate10h_monitor_soak.py --phase n10 --once --report
  .venv/bin/python scripts/gate10h_monitor_soak.py --phase n10 --duration 24h --interval 5m --allow-sparse-latency

  make gate10h-monitor-soak ARGS='--phase n50 --status'
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

DEFAULT_API = "https://dealhunter-production-api.onrender.com"
USER_AGENT = "SaveIQ-Gate10H-SoakMonitor/1.0"
PHASES = ("n10", "n25", "n50", "n100")
DEFAULT_BASELINE = "artifacts/gate10h_prod_baseline.json"
DEFAULT_STATE = "artifacts/gate10h_prod_neural_state.json"
CACHE_RE = re.compile(
    r'^cache_events_total\{(?P<labels>[^}]*)\}\s+(?P<val>[0-9.eE+-]+)\s*$'
)
LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"')

MAX_ERROR_RATE = 0.001  # 0.1%
LATENCY_MULTIPLIER = 1.10
MIN_CACHE_HIT = 0.60


class SoakMonitorError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def mark(ok: bool | None) -> str:
    if ok is True:
        return "PASS"
    if ok is False:
        return "FAIL"
    return "WARN"


def parse_duration(raw: str) -> float:
    text = str(raw).strip().lower()
    if text.endswith("h"):
        return float(text[:-1]) * 3600.0
    if text.endswith("m"):
        return float(text[:-1]) * 60.0
    if text.endswith("s"):
        return float(text[:-1])
    return float(text)


def load_prereq_module() -> Any:
    path = Path(__file__).resolve().parent / "gate10h_check_prod_prereq.py"
    spec = importlib.util.spec_from_file_location("gate10h_check_prod_prereq", path)
    if spec is None or spec.loader is None:
        raise SoakMonitorError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def require_prod_token() -> str:
    token = os.environ.get("PROD_ADMIN_TOKEN", "").strip()
    if not token:
        raise SoakMonitorError(
            "PROD_ADMIN_TOKEN required (production ADMIN_API_TOKEN, not staging).\n"
            "  export PROD_ADMIN_TOKEN='...'"
        )
    return token


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
        hint = " (wrong/missing PROD_ADMIN_TOKEN)" if exc.code == 401 else ""
        raise SoakMonitorError(f"GET {url} -> HTTP {exc.code}: {body[:400]}{hint}") from exc
    except Exception as exc:  # noqa: BLE001
        raise SoakMonitorError(f"GET {url} failed: {exc}") from exc


def http_json(url: str, *, token: str | None = None) -> dict[str, Any]:
    payload = http_text(url, token=token)
    data = json.loads(payload) if payload else {}
    if not isinstance(data, dict):
        raise SoakMonitorError(f"{url} did not return a JSON object")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def parse_cache_events(metrics: str) -> dict[str, float]:
    hits = 0.0
    misses = 0.0
    for line in metrics.splitlines():
        m = CACHE_RE.match(line)
        if not m:
            continue
        labels = {lm.group(1): lm.group(2) for lm in LABEL_RE.finditer(m.group("labels"))}
        val = float(m.group("val"))
        result = labels.get("result")
        if result == "hit":
            hits += val
        elif result == "miss":
            misses += val
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "total": total,
        "hit_rate": (hits / total) if total else 0.0,
    }


def cache_from_router_metrics(payload: dict[str, Any]) -> dict[str, float]:
    hits = float(payload.get("cache_hits") or 0)
    misses = float(payload.get("cache_misses") or 0)
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "total": total,
        "hit_rate": (hits / total) if total else 0.0,
        "source": "admin_router_metrics",
    }


def evaluate_tick(
    *,
    snap: dict[str, Any],
    cache: dict[str, float],
    bandit: dict[str, Any],
    safety: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
    prev_http_5xx: float | None,
    max_error_rate: float,
    latency_multiplier: float,
    min_cache_hit: float,
    allow_sparse_cache: bool,
    allow_sparse_latency: bool,
    require_neural_policy: bool,
    require_neural_ready: bool,
    allow_sparse_llm: bool,
    router_metrics: dict[str, Any] | None = None,
    expect_rlhf: bool = False,
) -> tuple[bool, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    http = snap.get("http") or {}
    total = float(http.get("total") or 0.0)
    five = float(http.get("5xx") or 0.0)
    rate = float(http.get("error_rate") or 0.0)

    delta_5xx: float | None = None if prev_http_5xx is None else max(0.0, five - prev_http_5xx)
    five_ok = five == 0.0 if delta_5xx is None else delta_5xx == 0.0
    checks.append(
        {
            "name": "http_5xx",
            "ok": five_ok,
            "detail": (
                f"cumulative_5xx={five:.0f} delta_5xx="
                f"{'n/a' if delta_5xx is None else f'{delta_5xx:.0f}'} "
                f"total={total:.0f}"
            ),
        }
    )

    rate_ok = rate < max_error_rate
    checks.append(
        {
            "name": "http_error_rate",
            "ok": rate_ok,
            "detail": f"error_rate={rate:.6f} threshold<{max_error_rate}",
        }
    )

    llm = snap.get("llm") or {}
    llm_total = float(llm.get("total") or 0.0)
    llm_rate = float(llm.get("error_rate") or 0.0)
    if llm_total <= 0:
        llm_ok: bool | None = None if allow_sparse_llm else False
        llm_detail = (
            f"sparse llm series (total={llm_total:.0f})"
            + ("; allowed via --allow-sparse-llm" if allow_sparse_llm else "")
        )
    else:
        llm_ok = llm_rate < max_error_rate
        llm_detail = (
            f"llm_error_rate={llm_rate:.6f} errors={llm.get('errors')} "
            f"total={llm_total:.0f} threshold<{max_error_rate}"
        )
    checks.append({"name": "llm_provider_errors", "ok": llm_ok, "detail": llm_detail})

    providers = (router_metrics or {}).get("providers") or {}
    prov_req = 0.0
    prov_err = 0.0
    if isinstance(providers, dict):
        for metrics in providers.values():
            if not isinstance(metrics, dict):
                continue
            prov_req += float(metrics.get("requests") or 0)
            prov_err += float(metrics.get("errors") or 0)
    if prov_req <= 0:
        prov_ok: bool | None = None if allow_sparse_llm else False
        prov_detail = "no /admin/router/metrics provider samples"
        if allow_sparse_llm:
            prov_detail += "; allowed via --allow-sparse-llm"
    else:
        prov_rate = prov_err / prov_req
        prov_ok = prov_rate < max_error_rate
        prov_detail = (
            f"router_provider_error_rate={prov_rate:.6f} "
            f"errors={prov_err:.0f} requests={prov_req:.0f} threshold<{max_error_rate}"
        )
    checks.append({"name": "router_provider_errors", "ok": prov_ok, "detail": prov_detail})

    lat = snap.get("latency_p95_ms") or {}
    base_lat = (baseline or {}).get("latency_p95_ms") or {}
    for path in ("/search", "/recommendations"):
        cur = lat.get(path)
        base = base_lat.get(path)
        if cur is None or base is None:
            ok: bool | None
            if allow_sparse_latency and (cur is None or base is None):
                ok = None
                detail = (
                    f"sparse p95 {path} baseline={base} current={cur}; "
                    "allowed via --allow-sparse-latency (histogram empty after redeploy?)"
                )
            else:
                ok = False
                detail = f"missing p95 {path} baseline={base} current={cur}"
        else:
            limit = float(base) * latency_multiplier
            ok = float(cur) <= limit
            detail = (
                f"p95_ms={float(cur):.1f} baseline={float(base):.1f} "
                f"limit={limit:.1f} (×{latency_multiplier})"
            )
        checks.append({"name": f"latency_p95{path}", "ok": ok, "detail": detail})

    cache_total = float(cache.get("total") or 0.0)
    hit_rate = float(cache.get("hit_rate") or 0.0)
    if cache_total <= 0:
        cache_ok: bool | None = None if allow_sparse_cache else False
        cache_detail = (
            "no cache samples"
            + ("; allowed via --allow-sparse-cache" if allow_sparse_cache else "")
        )
    else:
        cache_ok = hit_rate > min_cache_hit
        cache_detail = (
            f"hit_rate={hit_rate:.4f} hits={cache.get('hits')} "
            f"misses={cache.get('misses')} threshold>{min_cache_hit}"
        )
    checks.append({"name": "cache_hit_rate", "ok": cache_ok, "detail": cache_detail})

    flags = bandit.get("flags") or {}
    policy = str(bandit.get("policy") or "")
    neural = bandit.get("neural") or {}
    rlhf = bandit.get("rlhf") or {}
    if expect_rlhf:
        flag_ok = flags.get("rlhf") is True
        flag_detail = (
            f"policy={policy} flags.rlhf={flags.get('rlhf')} "
            f"flags.neural={flags.get('neural')} "
            f"rlhf.ready={rlhf.get('ready')} samples={rlhf.get('sample_count')}"
        )
    else:
        flag_ok = flags.get("neural") is True and flags.get("rlhf") is not True
        flag_detail = (
            f"policy={policy} flags.neural={flags.get('neural')} "
            f"flags.rlhf={flags.get('rlhf')} "
            f"neural.ready={neural.get('ready')} samples={neural.get('sample_count')}"
        )
    checks.append({"name": "bandit_flags", "ok": flag_ok, "detail": flag_detail})
    if expect_rlhf:
        checks.append(
            {
                "name": "policy_rlhf",
                "ok": policy.lower() == "rlhf",
                "detail": f"policy={policy}",
            }
        )
    elif require_neural_policy:
        checks.append(
            {
                "name": "policy_neural",
                "ok": policy.lower() == "neural",
                "detail": f"policy={policy}",
            }
        )
    ready = neural.get("ready") is True
    if require_neural_ready:
        checks.append(
            {
                "name": "neural_ready",
                "ok": ready,
                "detail": (
                    f"neural.ready={neural.get('ready')} "
                    f"samples={neural.get('sample_count')}"
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "neural_ready",
                "ok": True if ready else None,
                "detail": (
                    f"neural.ready={neural.get('ready')} samples={neural.get('sample_count')}"
                    + ("" if ready else "; WARN until min_samples_ready (not a soak blocker)")
                ),
            }
        )

    if safety:
        env = safety.get("env") or {}
        runtime = safety.get("runtime") or {}
        safe_ok = (
            env.get("feature_kill_switch") is not True
            and env.get("feature_auto_tuning") is not True
            and runtime.get("tripped") is not True
        )
        checks.append(
            {
                "name": "safety_kill_autotune_off",
                "ok": safe_ok,
                "detail": (
                    f"kill={env.get('feature_kill_switch')} "
                    f"autotune={env.get('feature_auto_tuning')} "
                    f"tripped={runtime.get('tripped')}"
                ),
            }
        )

    passed = all(c["ok"] is not False for c in checks)
    return passed, checks


def send_alerts(message: str, payload: dict[str, Any]) -> list[str]:
    sent: list[str] = []
    webhook = os.environ.get("SOAK_ALERT_WEBHOOK_URL", "").strip()
    if webhook:
        try:
            body = json.dumps({"text": message, "payload": payload}).encode("utf-8")
            req = urllib.request.Request(
                webhook,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            sent.append("webhook")
        except Exception as exc:  # noqa: BLE001
            log(f"alert_webhook_failed={exc}")

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat:
        try:
            url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            data = urllib.parse.urlencode(
                {"chat_id": tg_chat, "text": message[:3500]}
            ).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            sent.append("telegram")
        except Exception as exc:  # noqa: BLE001
            log(f"alert_telegram_failed={exc}")

    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_to = os.environ.get("SMTP_TO", "").strip()
    smtp_from = os.environ.get("SMTP_FROM", "").strip() or smtp_to
    if smtp_host and smtp_to:
        try:
            msg = EmailMessage()
            msg["Subject"] = "Gate 10H soak ALERT"
            msg["From"] = smtp_from
            msg["To"] = smtp_to
            msg.set_content(message)
            with smtplib.SMTP(smtp_host, int(os.environ.get("SMTP_PORT", "25")), timeout=15) as smtp:
                smtp.send_message(msg)
            sent.append("email")
        except Exception as exc:  # noqa: BLE001
            log(f"alert_email_failed={exc}")

    return sent


def soak_remaining(state: dict[str, Any], phase: str, soak_seconds: float) -> dict[str, Any]:
    phases = state.get("phases") or {}
    meta = phases.get(phase) or {}
    started = float(meta.get("started_at_epoch") or 0)
    if started <= 0:
        return {"ok": False, "error": f"{phase}_not_started", "phase": phase}
    now = time.time()
    elapsed = now - started
    left = max(0.0, soak_seconds - elapsed)
    return {
        "ok": True,
        "phase": phase,
        "started_at": meta.get("started_at"),
        "elapsed_s": elapsed,
        "remaining_s": left,
        "complete": left <= 0,
        "target_pct": meta.get("target_pct"),
    }


def collect_tick(
    *,
    api_url: str,
    token: str,
    prereq: Any,
    baseline: dict[str, Any] | None,
    prev_http_5xx: float | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    metrics_text = http_text(f"{api_url}/metrics", token=token)
    snap = prereq.parse_prometheus_snapshot(metrics_text)
    prom_cache = parse_cache_events(metrics_text)

    router_metrics: dict[str, Any] = {}
    try:
        router_metrics = http_json(f"{api_url}/admin/router/metrics", token=token)
    except SoakMonitorError as exc:
        router_metrics = {"error": str(exc)}

    admin_cache = cache_from_router_metrics(router_metrics) if "error" not in router_metrics else {}
    # Prefer Prometheus cache series; fall back to admin snapshot.
    cache = prom_cache if prom_cache.get("total") else admin_cache or prom_cache

    bandit = http_json(f"{api_url}/admin/bandit/status", token=token)
    safety: dict[str, Any] | None = None
    try:
        safety = http_json(f"{api_url}/admin/safety/status", token=token)
    except SoakMonitorError as exc:
        safety = {"error": str(exc)}

    passed, checks = evaluate_tick(
        snap=snap,
        cache=cache,
        bandit=bandit,
        safety=safety if "error" not in (safety or {}) else None,
        baseline=baseline,
        prev_http_5xx=prev_http_5xx,
        max_error_rate=args.max_error_rate,
        latency_multiplier=args.latency_multiplier,
        min_cache_hit=args.min_cache_hit,
        allow_sparse_cache=args.allow_sparse_cache,
        allow_sparse_latency=args.allow_sparse_latency,
        require_neural_policy=args.require_neural_policy,
        require_neural_ready=args.require_neural_ready,
        allow_sparse_llm=args.allow_sparse_llm,
        router_metrics=router_metrics if "error" not in router_metrics else None,
        expect_rlhf=args.expect_rlhf,
    )
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "breach": not passed,
        "checks": checks,
        "snapshot": snap,
        "cache": cache,
        "bandit": {
            "policy": bandit.get("policy"),
            "flags": bandit.get("flags"),
            "neural": bandit.get("neural"),
        },
        "router_metrics": {
            "cache_hits": router_metrics.get("cache_hits"),
            "cache_misses": router_metrics.get("cache_misses"),
            "providers": router_metrics.get("providers"),
            "error": router_metrics.get("error"),
        },
        "safety_error": (safety or {}).get("error"),
    }


def write_summary(
    *,
    repo: Path,
    phase: str,
    ticks: list[dict[str, Any]],
    soak: dict[str, Any],
    args: argparse.Namespace,
) -> Path:
    breaches = [t for t in ticks if t.get("breach")]
    summary = {
        "phase": phase,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL" if breaches else "PASS",
        "ticks": len(ticks),
        "breaches": len(breaches),
        "soak": soak,
        "last": ticks[-1] if ticks else None,
        "thresholds": {
            "max_error_rate": args.max_error_rate,
            "latency_multiplier": args.latency_multiplier,
            "min_cache_hit": args.min_cache_hit,
            "allow_sparse_cache": args.allow_sparse_cache,
            "allow_sparse_latency": args.allow_sparse_latency,
            "allow_sparse_llm": args.allow_sparse_llm,
            "require_neural_ready": args.require_neural_ready,
        },
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = repo / "artifacts" / f"gate10h_soak_report_{phase}_{stamp}.json"
    save_json(path, summary)
    save_json(repo / "artifacts" / f"gate10h_soak_report_{phase}_latest.json", summary)
    return path


def fmt_hours(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{hours}h{minutes:02d}m"


def run_status(args: argparse.Namespace) -> int:
    repo = Path(__file__).resolve().parents[1]
    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = repo / state_path
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    soak = soak_remaining(state, args.phase, parse_duration(args.soak_window))
    latest = repo / "artifacts" / f"gate10h_soak_report_{args.phase}_latest.json"
    jsonl = repo / "artifacts" / f"gate10h_soak_monitor_{args.phase}.jsonl"
    log(f"gate10h_soak=status phase={args.phase}")
    log(
        f"  soak_complete={soak.get('complete')} elapsed={fmt_hours(float(soak.get('elapsed_s') or 0))} "
        f"remaining={fmt_hours(float(soak.get('remaining_s') or 0))} started={soak.get('started_at')}"
    )
    if latest.is_file():
        report = json.loads(latest.read_text(encoding="utf-8"))
        log(
            f"  latest_report status={report.get('status')} ticks={report.get('ticks')} "
            f"breaches={report.get('breaches')} checked_at={report.get('checked_at')}"
        )
    else:
        log(f"  latest_report=missing ({latest})")
    if jsonl.is_file():
        last_line = ""
        with jsonl.open(encoding="utf-8") as handle:
            for last_line in handle:
                pass
        if last_line.strip():
            rec = json.loads(last_line)
            log(f"  last_tick ts={rec.get('ts')} passed={rec.get('passed')} breach={rec.get('breach')}")
    return 0 if soak.get("ok") else 1


def run(args: argparse.Namespace) -> int:
    repo = Path(__file__).resolve().parents[1]
    api_url = args.api_url.rstrip("/")
    prereq = load_prereq_module()

    baseline: dict[str, Any] | None = None
    bpath = Path(args.baseline)
    if not bpath.is_absolute():
        bpath = repo / bpath
    if bpath.is_file():
        baseline = json.loads(bpath.read_text(encoding="utf-8"))
        log(f"baseline_loaded={bpath} captured_at={baseline.get('captured_at')}")
    else:
        log(f"WARN: baseline missing at {bpath} — latency checks will FAIL")

    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = repo / state_path
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    soak = soak_remaining(state, args.phase, parse_duration(args.soak_window))
    log(
        f"gate10h_soak=start phase={args.phase} once={args.once} "
        f"duration={args.duration} interval={args.interval} "
        f"soak_complete={soak.get('complete')} remaining={soak.get('remaining_s')}"
    )

    if args.dry_run:
        log("[DRY RUN] would poll /admin/bandit/status + /metrics + /admin/router/metrics")
        log(f"[DRY RUN] jsonl=artifacts/gate10h_soak_monitor_{args.phase}.jsonl")
        return 0

    token = require_prod_token()
    jsonl_path = repo / "artifacts" / f"gate10h_soak_monitor_{args.phase}.jsonl"
    duration_s = 0.0 if args.once else parse_duration(args.duration)
    interval_s = parse_duration(args.interval)
    deadline = time.time() + duration_s
    ticks: list[dict[str, Any]] = []
    prev_5xx: float | None = None
    worst = 0

    while True:
        try:
            tick = collect_tick(
                api_url=api_url,
                token=token,
                prereq=prereq,
                baseline=baseline,
                prev_http_5xx=prev_5xx,
                args=args,
            )
        except SoakMonitorError as exc:
            tick = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "passed": False,
                "breach": True,
                "error": str(exc),
                "checks": [{"name": "collect", "ok": False, "detail": str(exc)}],
            }
        tick["phase"] = args.phase
        tick["soak"] = soak_remaining(state, args.phase, parse_duration(args.soak_window))
        ticks.append(tick)
        append_jsonl(jsonl_path, tick)

        http = (tick.get("snapshot") or {}).get("http") or {}
        if "5xx" in http:
            prev_5xx = float(http.get("5xx") or 0.0)

        status = "ok" if tick.get("passed") else "BREACH"
        log(f"gate10h_soak=tick {status} ts={tick['ts']}")
        for item in tick.get("checks") or []:
            log(f"  {mark(item.get('ok'))} {item.get('name')}: {item.get('detail')}")

        if tick.get("breach"):
            worst = 2
            fails = [
                c for c in (tick.get("checks") or []) if c.get("ok") is False
            ]
            msg = (
                f"Gate 10H soak ALERT phase={args.phase} "
                + "; ".join(f"{c['name']}: {c['detail']}" for c in fails)
            )
            log(f"ALERT {msg}")
            sent = send_alerts(msg, tick)
            if sent:
                log(f"alert_sent={','.join(sent)}")
            if args.exit_on_breach:
                break

        if args.once:
            break
        if time.time() >= deadline:
            break
        time.sleep(max(1.0, interval_s))

    report_path = write_summary(
        repo=repo, phase=args.phase, ticks=ticks, soak=soak, args=args
    )
    log(f"jsonl_written={jsonl_path}")
    log(f"report_written={report_path}")
    final = "FAIL" if worst else "PASS"
    log(f"gate10h_soak={final.lower()} phase={args.phase} ticks={len(ticks)}")
    if args.report:
        pass  # report always written; flag kept for operator habit
    return worst


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gate 10H production neural soak monitor")
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--duration", default="24h", help="Loop length (e.g. 24h, 60m)")
    parser.add_argument("--interval", default="5m", help="Sample interval (e.g. 5m, 10m)")
    parser.add_argument("--once", action="store_true", help="Single sample then exit")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print soak remaining + latest report; no poll loop",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true", help="Always write summary JSON")
    parser.add_argument("--exit-on-breach", action="store_true")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("PROD_API_URL") or os.environ.get("API_URL", DEFAULT_API),
    )
    parser.add_argument("--baseline", default=str(repo / DEFAULT_BASELINE))
    parser.add_argument("--state-file", default=str(repo / DEFAULT_STATE))
    parser.add_argument(
        "--soak-window",
        default="24h",
        help="Expected soak length for remaining-time (default 24h)",
    )
    parser.add_argument("--max-error-rate", type=float, default=MAX_ERROR_RATE)
    parser.add_argument("--latency-multiplier", type=float, default=LATENCY_MULTIPLIER)
    parser.add_argument("--min-cache-hit", type=float, default=MIN_CACHE_HIT)
    parser.add_argument(
        "--allow-sparse-cache",
        action="store_true",
        default=True,
        help="WARN (not FAIL) when cache series is empty (default on)",
    )
    parser.add_argument("--strict-cache", action="store_true", help="FAIL if cache series empty")
    parser.add_argument("--allow-sparse-latency", action="store_true")
    parser.add_argument(
        "--allow-sparse-llm",
        action="store_true",
        default=True,
        help="WARN (not FAIL) when llm_requests_total / router providers are empty (default on)",
    )
    parser.add_argument(
        "--strict-llm",
        action="store_true",
        help="FAIL if LLM/provider series is empty",
    )
    parser.add_argument(
        "--require-neural-policy",
        action="store_true",
        default=True,
        help="Require runtime policy=neural (default on)",
    )
    parser.add_argument(
        "--allow-any-policy",
        action="store_true",
        help="Do not require policy=neural",
    )
    parser.add_argument(
        "--require-neural-ready",
        action="store_true",
        help="FAIL unless neural.ready=true (default is WARN; live soak still has 0 samples)",
    )
    parser.add_argument(
        "--expect-rlhf",
        action="store_true",
        help="RLHF canary soak: require policy=rlhf and flags.rlhf=true (neural may stay on)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.strict_cache:
        args.allow_sparse_cache = False
    if args.strict_llm:
        args.allow_sparse_llm = False
    if args.allow_any_policy or args.expect_rlhf:
        args.require_neural_policy = False
    if not hasattr(args, "require_neural_ready"):
        args.require_neural_ready = False
    if not hasattr(args, "allow_sparse_llm"):
        args.allow_sparse_llm = True
    try:
        if args.status:
            return run_status(args)
        return run(args)
    except SoakMonitorError as exc:
        log(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
