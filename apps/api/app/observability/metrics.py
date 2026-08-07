"""Prometheus metrics for Gate 10B SLIs."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 5.0, 10.0),
)
LLM_REQUESTS = Counter(
    "llm_requests_total",
    "LLM / router provider requests",
    ["provider", "result"],
)
LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM / router provider latency in seconds",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)
LLM_COST = Counter(
    "llm_cost_usd_total",
    "Estimated LLM cost in USD",
    ["provider"],
)
CACHE_EVENTS = Counter(
    "cache_events_total",
    "Router cache hit/miss events",
    ["result"],
)
RECOMMENDATIONS = Counter(
    "recommendations_total",
    "Recommendation responses",
    ["strategy"],
)
BANDIT_REGRET = Counter(
    "bandit_regret_total",
    "Accumulated bandit regret (units defined by reward scale)",
)
ROUTER_FALLBACKS = Counter(
    "router_fallback_total",
    "AI router fallbacks to deterministic path",
    ["reason"],
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


def observe_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    route = _normalize_path(path)
    HTTP_REQUESTS.labels(method=method.upper(), path=route, status_code=str(status_code)).inc()
    HTTP_REQUEST_DURATION.labels(method=method.upper(), path=route).observe(
        max(duration_seconds, 0.0)
    )


def observe_llm_request(
    *,
    provider: str,
    latency_ms: float,
    estimated_cost_usd: float,
    error: bool,
) -> None:
    result = "error" if error else "ok"
    LLM_REQUESTS.labels(provider=provider, result=result).inc()
    LLM_REQUEST_DURATION.labels(provider=provider).observe(max(latency_ms, 0.0) / 1000.0)
    if estimated_cost_usd > 0:
        LLM_COST.labels(provider=provider).inc(estimated_cost_usd)


def observe_cache(*, hit: bool) -> None:
    CACHE_EVENTS.labels(result="hit" if hit else "miss").inc()


def observe_recommendation(*, strategy: str) -> None:
    RECOMMENDATIONS.labels(strategy=strategy or "unknown").inc()


def observe_router_fallback(*, reason: str) -> None:
    ROUTER_FALLBACKS.labels(reason=reason or "unknown").inc()


def observe_bandit_regret(amount: float = 1.0) -> None:
    BANDIT_REGRET.inc(max(amount, 0.0))


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
