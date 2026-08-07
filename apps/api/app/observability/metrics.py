"""Prometheus metrics for Gate 10B/10C/10D SLIs."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code", "canary", "ab_group"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path", "canary", "ab_group"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 5.0, 10.0),
)
LLM_REQUESTS = Counter(
    "llm_requests_total",
    "LLM / router provider requests",
    ["provider", "result", "canary", "ab_group"],
)
LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM / router provider latency in seconds",
    ["provider", "canary", "ab_group"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)
LLM_COST = Counter(
    "llm_cost_usd_total",
    "Estimated LLM cost in USD",
    ["provider", "canary", "ab_group"],
)
CACHE_EVENTS = Counter(
    "cache_events_total",
    "Router cache hit/miss events",
    ["result", "canary", "ab_group"],
)
RECOMMENDATIONS = Counter(
    "recommendations_total",
    "Recommendation responses",
    ["strategy", "canary", "ab_group"],
)
BANDIT_REGRET = Counter(
    "bandit_regret_total",
    "Accumulated bandit regret (units defined by reward scale)",
    ["canary", "ab_group"],
)
ROUTER_FALLBACKS = Counter(
    "router_fallback_total",
    "AI router fallbacks to deterministic path",
    ["reason", "canary", "ab_group"],
)


def _normalize_path(path: str) -> str:
    if path.startswith("/admin"):
        return "/admin/*"
    if path.startswith("/offers/"):
        return "/offers/{id}"
    if path.startswith("/api/"):
        return path
    known = {
        "/health",
        "/metrics",
        "/search",
        "/recommendations",
        "/bandit/status",
        "/personalization/status",
        "/user/profile",
        "/user/recommendations",
        "/user/feedback",
        "/user/opt-out",
        "/clicks",
    }
    return path if path in known else "/other"


def _canary_label(explicit: str | None = None) -> str:
    if explicit is not None:
        return explicit
    from app.services.canary.context import get_canary_cohort_label

    cohort = get_canary_cohort_label()
    if cohort == "canary":
        return "true"
    if cohort == "control":
        return "false"
    return "off"


def _ab_group_label(explicit: str | None = None) -> str:
    if explicit is not None:
        return explicit or "none"
    from app.services.abtest.context import get_ab_group

    return get_ab_group() or "none"


def observe_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
    canary: str | None = None,
    ab_group: str | None = None,
) -> None:
    route = _normalize_path(path)
    canary_label = _canary_label(canary)
    ab_label = _ab_group_label(ab_group)
    HTTP_REQUESTS.labels(
        method=method.upper(),
        path=route,
        status_code=str(status_code),
        canary=canary_label,
        ab_group=ab_label,
    ).inc()
    HTTP_REQUEST_DURATION.labels(
        method=method.upper(),
        path=route,
        canary=canary_label,
        ab_group=ab_label,
    ).observe(max(duration_seconds, 0.0))


def observe_llm_request(
    *,
    provider: str,
    latency_ms: float,
    estimated_cost_usd: float,
    error: bool,
    canary: str | None = None,
    ab_group: str | None = None,
) -> None:
    result = "error" if error else "ok"
    canary_label = _canary_label(canary)
    ab_label = _ab_group_label(ab_group)
    LLM_REQUESTS.labels(
        provider=provider, result=result, canary=canary_label, ab_group=ab_label
    ).inc()
    LLM_REQUEST_DURATION.labels(provider=provider, canary=canary_label, ab_group=ab_label).observe(
        max(latency_ms, 0.0) / 1000.0
    )
    if estimated_cost_usd > 0:
        LLM_COST.labels(provider=provider, canary=canary_label, ab_group=ab_label).inc(
            estimated_cost_usd
        )


def observe_cache(*, hit: bool, canary: str | None = None, ab_group: str | None = None) -> None:
    CACHE_EVENTS.labels(
        result="hit" if hit else "miss",
        canary=_canary_label(canary),
        ab_group=_ab_group_label(ab_group),
    ).inc()


def observe_recommendation(
    *, strategy: str, canary: str | None = None, ab_group: str | None = None
) -> None:
    RECOMMENDATIONS.labels(
        strategy=strategy or "unknown",
        canary=_canary_label(canary),
        ab_group=_ab_group_label(ab_group),
    ).inc()


def observe_router_fallback(
    *, reason: str, canary: str | None = None, ab_group: str | None = None
) -> None:
    ROUTER_FALLBACKS.labels(
        reason=reason or "unknown",
        canary=_canary_label(canary),
        ab_group=_ab_group_label(ab_group),
    ).inc()


def observe_bandit_regret(
    amount: float = 1.0, *, canary: str | None = None, ab_group: str | None = None
) -> None:
    BANDIT_REGRET.labels(
        canary=_canary_label(canary),
        ab_group=_ab_group_label(ab_group),
    ).inc(max(amount, 0.0))


KILL_SWITCH_TRIPS = Counter(
    "kill_switch_trips_total",
    "Kill switch trip events (Gate 10E)",
    ["reason_class"],
)
AUTO_TUNE_ACTIONS = Counter(
    "auto_tune_actions_total",
    "Auto-tune propose/apply events (Gate 10E)",
    ["result"],
)


def observe_kill_switch_trip(*, reason: str) -> None:
    reason_class = "unknown"
    lowered = (reason or "").lower()
    if lowered.startswith("error_rate"):
        reason_class = "error_rate"
    elif lowered.startswith("latency"):
        reason_class = "latency"
    elif lowered.startswith("cost"):
        reason_class = "cost"
    elif "manual" in lowered:
        reason_class = "manual"
    else:
        reason_class = "other"
    KILL_SWITCH_TRIPS.labels(reason_class=reason_class).inc()


def observe_auto_tune_action(*, result: str) -> None:
    AUTO_TUNE_ACTIONS.labels(result=result or "unknown").inc()


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
