# Gate 10D Closeout — A/B Testing Framework

Date: 2026-08-07  
Branch: `feature/gate-10d-abtest`

## Summary

Gate 10D adds a production-ready **A/B / holdout** framework: sticky MD5 assignment,
Redis-backed membership (30-day TTL), YAML experiment config, admin start/stop/significance
APIs, Prometheus `ab_group` labels, and Grafana comparison panels.  
**Default:** `FEATURE_ABTEST_ENABLED=false` (no assignment until admin start).

## Delivered

| Item | Location |
| --- | --- |
| Settings / config accessors | `FEATURE_ABTEST_*`, `app/core/config.py` |
| Sample experiment YAML | `config/abtest.yaml`, `apps/api/config/abtest.yaml` |
| `ABTestService` | `app/services/abtest/service.py` |
| Middleware (`X-User-ID`, `X-AB-Group`) | `app/middleware/abtest.py` |
| Admin API | `/admin/abtest/*` |
| Effective flag overrides → router | `canary/effective.py` + AiRouter |
| Metrics label `ab_group` | `app/observability/metrics.py` |
| Grafana A/B panels | `monitoring/grafana-dashboard.json` |
| Runbook §3c | `docs/RUNBOOK.md` |
| Tests | `apps/api/tests/test_abtest.py` |
| Smoke check (must stay off) | `scripts/production_smoke.py` |

## Holdout design (`router_holdout_v1`)

| Group | Share | Behavior |
| --- | ---: | --- |
| `control` | 50% | Rule-based / router off |
| `treatment_a` | 50% | AI router **mock** path |

Significance: `scipy.stats.chi2_contingency` on exposure/conversion counts.

## Validation

```bash
cd apps/api && pip install -e ".[dev]"
ruff check app tests && mypy app && pytest
```

## Exit criteria

- [x] Framework + admin controls + sticky Redis keys
- [x] Router respects A/B overrides
- [x] Metrics + Grafana + runbook
- [x] Defaults off; smoke asserts A/B not running
- [ ] Production image pin + Sync (operator)
- [ ] Intentional start only after canary stage is approved
