# Service Level Objectives (Gate 10B)

Environment: production (`saveiq-production`)  
Related: `docs/GATE_10_PLAN.md`, `monitoring/alerts.yml`, `docs/RUNBOOK.md`

## Principles

- Feature flags for AI/bandit/personalization remain **off** until Gate 10C canary evidence.
- Cold-start on Render starter plans can inflate p95; alert on **sustained** windows, not single spikes.
- Cost SLOs only apply when live LLM providers are enabled.

## Target SLOs (steady state)

| SLO | Objective | Notes |
| --- | --- | --- |
| Availability | 99.9% monthly | `/health` success from external probe |
| API latency | p95 < 500ms | Warm `/search`, `/recommendations` |
| LLM latency | p99 < 1s | Live provider calls only |
| Error rate | 5xx < 1% | Rolling 5–15 minutes |
| Cost | < $0.01 / recommendation | Estimated token cost when AI router live |
| Cache hit rate | > 70% | AI router cache when enabled |

## Bootstrapping thresholds (Gate 10B alerts)

Until one week of baseline exists, alerts use looser thresholds aligned with Gate 10A plan:

| Signal | Alert when |
| --- | --- |
| Availability | < 99.5% over 24h (probe failures) |
| API p95 | > 1.5s for 5 minutes |
| 5xx rate | > 1% for 5 minutes (critical if > 5%) |
| LLM provider errors | > 5% of live calls for 2 minutes |
| Cache hit rate | < 50% for 10 minutes (when cache traffic > 0) |
| Estimated cost | > $10 / hour |

## SLIs (Prometheus)

| SLI | Metric |
| --- | --- |
| Request rate / errors | `http_requests_total{status_code=…}` |
| Latency | `http_request_duration_seconds` (histogram) |
| LLM calls | `llm_requests_total{provider,result}` |
| LLM latency | `llm_request_duration_seconds{provider}` |
| LLM cost | `llm_cost_usd_total{provider}` |
| Cache | `cache_events_total{result="hit\|miss"}` |
| Recommendations | `recommendations_total{strategy}` |
| Bandit regret | `bandit_regret_total` |
| Router fallbacks | `router_fallback_total{reason}` |

Scrape: `GET /metrics` (optional `X-Metrics-Token` when `METRICS_TOKEN` is set).

## Error budget

At 99.9% monthly availability ≈ **43 minutes** downtime/month.  
Spend budget only on deliberate deploys/canaries; freeze risky flag flips when budget < 25% remaining.
