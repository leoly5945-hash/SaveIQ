# Gate 10C Closeout — Canary Deployment

Date: 2026-08-07  
Branch: `feature/gate-10c-canary`

## Summary

Gate 10C adds **sticky hash-based canary** for AI features (`router`, `bandit`,
`personalization`, `llm_cn`) with admin runtime controls, Prometheus `canary`
labels, Grafana comparison panels, and a phased runbook. **Defaults remain off**
(`CANARY_ENABLED=false`, `CANARY_PERCENTAGE=0`, global `FEATURE_*=false`).

## Delivered

| Item | Location |
| --- | --- |
| Canary settings | `CANARY_*` in `app/core/settings.py`, `.env.example`, `render-production.yaml` |
| `CanaryService` (hash, Redis sticky 24h, runtime config) | `app/services/canary/` |
| Effective feature resolution | `app/services/canary/effective.py` |
| Request identity middleware | `app/middleware/canary.py` |
| Admin API | `GET/POST /admin/canary/*` |
| Metrics label `canary` | `app/observability/metrics.py` |
| Grafana canary vs control panels | `monitoring/grafana-dashboard.json` |
| Runbook phases + rollback | `docs/RUNBOOK.md` §3b |
| Production smoke canary checks | `scripts/production_smoke.py` |
| Unit/API tests | `apps/api/tests/test_canary.py` |

## Behavior

- **Canary off:** existing global `FEATURE_*` flags only.
- **Canary on:** cohort `hash(identity[:feature]) % 100 < percentage` gets listed
  features even when global flags are false; control stays on the rule-based path.
- Sticky assignment cached in Redis (or memory) for 24h when `CANARY_STICKY_SESSION=true`.
- Safe modes: canary-enabled router with `AI_ROUTER_MODE=disabled` coerces to **mock**;
  bandit coerces to **logging**.

## Phases

C0 0% → C1 1% → C2 5% → C3 25% → C4 100% (soak ≥24h each).  
Rollback: `POST /admin/canary/config` `{"enabled":false,"percentage":0}`.

## Validation

```bash
cd apps/api && .venv/bin/ruff check app tests && .venv/bin/mypy app && .venv/bin/pytest
PYTHON=.venv/bin/python make production-smoke   # after image pin + deploy
```

## Exit criteria

- [x] Canary service + sticky assignment
- [x] Feature-flag integration (router / bandit / personalization / llm_cn)
- [x] Admin status / config / stats
- [x] Metrics + Grafana canary panels
- [x] Runbook + closeout + roadmap
- [ ] Production image pin + Render Sync + smoke (operator)
- [ ] Intentional C1 (1%) only after observability dashboards are live
