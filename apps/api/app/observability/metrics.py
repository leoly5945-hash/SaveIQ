"""Prometheus metrics for Gate 10B/10C SLIs."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code", "canary"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path", "canary"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 5.0, 10.0),
)
LLM_REQUESTS = Counter(
    "llm_requests_total",
    "LLM / router provider requests",
    ["provider", "result", "canary"],
)
LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM / router provider latency in seconds",
    ["provider", "canary"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)
LLM_COST = Counter(
    "llm_cost_usd_total",
    "Estimated LLM cost in USD",
    ["provider", "canary"],
)
CACHE_EVENTS = Counter(
    "cache_events_total",
    "Router cache hit/miss events",
    ["result", "canary"],
)
RECOMMENDATIONS = Counter(
    "recommendations_total",
    "Recommendation responses",
    ["strategy", "canary"],
)
BANDIT_REGRET = Counter(
    "bandit_regret_total",
    "Accumulated bandit regret (units defined by reward scale)",
    ["canary"],
)
ROUTER_FALLBACKS = Counter(
    "router_fallback_total",
    "AI router fallbacks to deterministic path",
    ["reason", "canary"],
)


def _normalize_path(path: str) -> str:
    if path.startswith("/admin"):
        return "/admin/*"
    if path.startswith("/offers/"):
        return "/offers/{id}"
    if path.startswith("/api/"):
        return path
    # Keep low-cardinality public routes; bucket the rest.
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


def observe_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
    canary: str | None = None,
) -> None:
    route = _normalize_path(path)
    label = _canary_label(canary)
    HTTP_REQUESTS.labels(
        method=method.upper(),
        path=route,
        status_code=str(status_code),
        canary=label,
    ).inc()
    HTTP_REQUEST_DURATION.labels(method=method.upper(), path=route, canary=label).observe(
        max(duration_seconds, 0.0)
    )


def observe_llm_request(
    *,
    provider: str,
    latency_ms: float,
    estimated_cost_usd: float,
    error: bool,
    canary: str | None = None,
) -> None:
    result = "error" if error else "ok"
    label = _canary_label(canary)
    LLM_REQUESTS.labels(provider=provider, result=result, canary=label).inc()
    LLM_REQUEST_DURATION.labels(provider=provider, canary=label).observe(
        max(latency_ms, 0.0) / 1000.0
    )
    if estimated_cost_usd > 0:
        LLM_COST.labels(provider=provider, canary=label).inc(estimated_cost_usd)


def observe_cache(*, hit: bool, canary: str | None = None) -> None:
    CACHE_EVENTS.labels(result="hit" if hit else "miss", canary=_canary_label(canary)).inc()


def observe_recommendation(*, strategy: str, canary: str | None = None) -> None:
    RECOMMENDATIONS.labels(strategy=strategy or "unknown", canary=_canary_label(canary)).inc()


def observe_router_fallback(*, reason: str, canary: str | None = None) -> None:
    ROUTER_FALLBACKS.labels(reason=reason or "unknown", canary=_canary_label(canary)).inc()


def observe_bandit_regret(amount: float = 1.0, *, canary: str | None = None) -> None:
    BANDIT_REGRET.labels(canary=_canary_label(canary)).inc(max(amount, 0.0))


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
