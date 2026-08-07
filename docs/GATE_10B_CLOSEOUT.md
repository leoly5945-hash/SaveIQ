# Gate 10B Closeout — Observability, SLOs, Alerts

Date: 2026-08-07  
Branch: `feature/gate-10b-observability`

## Summary

Gate 10B adds production-ready **SLIs/SLOs**, **JSON structured request logs**, a Prometheus
**`/metrics`** endpoint, Grafana/Alertmanager templates, and alert playbooks in the runbook.
AI feature flags remain off; cost/LLM alerts only matter after canary enablement.

## Delivered

| Item | Location |
| --- | --- |
| SLO / SLI definitions | `docs/SLOS.md` |
| Structured logging (`structlog` JSON) | `app/core/logging.py`, request middleware |
| Prometheus metrics | `app/observability/metrics.py`, `GET /metrics` |
| Router → Prometheus bridge | `RouterMetrics.record_request` |
| Recommendation counter | `recommendations_total{strategy}` |
| Alert rules | `monitoring/alerts.yml` |
| Alertmanager + Slack template | `monitoring/alertmanager.yml` |
| Prometheus scrape example | `monitoring/prometheus.yml` |
| Grafana dashboard JSON | `monitoring/grafana-dashboard.json` |
| Runbook alert playbooks | `docs/RUNBOOK.md` |
| Production smoke `/metrics` check | `scripts/production_smoke.py` |
| Blueprint env | `STRUCTURED_LOGGING`, `METRICS_ENABLED`, `METRICS_TOKEN` (sync false) |

## Env knobs

| Variable | Default | Notes |
| --- | --- | --- |
| `STRUCTURED_LOGGING` | `true` | JSON logs to stdout |
| `METRICS_ENABLED` | `true` | Serve `/metrics` |
| `METRICS_TOKEN` | unset | If set, require `X-Metrics-Token` or admin token |

## Validation

```bash
cd apps/api && pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy app && pytest
PYTHON=.venv/bin/python make production-provision-validate
```

After image pin + deploy:

```bash
curl -sS "$API_URL/metrics" | head
ADMIN_API_TOKEN=... PYTHON=.venv/bin/python make production-smoke
```

## Operator follow-ups

- [ ] Deploy Prometheus (or Grafana Cloud / Datadog) scraping production `/metrics`
- [ ] Import `monitoring/grafana-dashboard.json`
- [ ] Set `SLACK_WEBHOOK_URL` for Alertmanager (never commit)
- [ ] Optionally set production `METRICS_TOKEN` and configure scraper auth
- [ ] Run a staged alert drill (force a warning, confirm Slack, resolve)

## Exit criteria

- [x] SLOs documented
- [x] Structured logs + `/metrics` in API
- [x] Alert rules + runbook playbooks
- [x] Smoke checks Prometheus surface
- [ ] External scrape + Slack drill (operator)
