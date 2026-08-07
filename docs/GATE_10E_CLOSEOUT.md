# Gate 10E Closeout — Kill Switch + Guardrailed Auto-Tune

Date: 2026-08-07  
Branch: `feature/gate-10e-auto-tune-kill-switch`

## Summary

Gate 10E adds a production-ready **safety orchestrator**: sliding-window kill switch
(error rate / latency p95 / cost) and cap-bounded auto-tune for router bandit hparams
(epsilon, α/β/γ) plus cache TTL. Admin APIs cover status, evaluate, trip/disarm, and
manual override.  
**Default:** `FEATURE_KILL_SWITCH=false`, `FEATURE_AUTO_TUNING=false`,
`AUTO_TUNE_DRY_RUN=true`, `AUTO_TUNE_CANARY_ENABLED=false`.

## Delivered

| Item | Location |
| --- | --- |
| Settings / caps / thresholds | `FEATURE_KILL_SWITCH`, `FEATURE_AUTO_TUNING`, `KILL_SWITCH_*`, `AUTO_TUNE_*` |
| `SafetyService` + metrics window | `app/services/safety/` |
| Admin API | `/admin/safety/*` |
| Request-path recording + background tick | `middleware/request_logging.py` |
| Bandit runtime hparams | `BanditRouterService.apply_runtime_hparams` |
| Cache TTL override | `router/runtime_overrides.py` |
| Prometheus counters | `kill_switch_trips_total`, `auto_tune_actions_total` |
| Grafana panels | `monitoring/grafana-dashboard.json` |
| Runbook §3d | `docs/RUNBOOK.md` |
| Tests | `apps/api/tests/test_safety.py` |
| Smoke (must stay env-off / not tripped) | `scripts/production_smoke.py` |
| Production Blueprint defaults | `render-production.yaml` |

## Integration rules (no conflict with 10C/10D)

- Kill switch **may** stop A/B and zero canary on breach (intentional safe rollback).
- Auto-tune **does not** change canary % unless `AUTO_TUNE_CANARY_ENABLED` / runtime flag.
- When A/B is running, canary auto-step is skipped.
- Neural / RLHF / Chinese / `BANDIT_POLICY` remain human-only.
- `manual_override=true` freezes automatic actions immediately.

## Validation

```bash
cd apps/api && pip install -e ".[dev]"
ruff check app tests && mypy app && pytest tests/test_safety.py
python scripts/validate_render_blueprint.py
```

## Exit criteria

- [x] Framework + admin controls + audit log
- [x] Caps enforced; dry-run default
- [x] Kill actions stop A/B + zero canary + reset hparams
- [x] Defaults off in production Blueprint; smoke asserts env off
- [ ] 7-day staging dry-run + kill drill before production enable (ops)
