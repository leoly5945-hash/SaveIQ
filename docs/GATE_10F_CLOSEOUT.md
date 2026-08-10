# Gate 10F Closeout — global AI router (mock)

## Scope

Enable **global** `FEATURE_AI_ROUTER=true` with `AI_ROUTER_MODE=mock` on production via Blueprint + Render Sync.

Out of scope (separate checklist):

- `AI_ROUTER_MODE=live`
- Chinese / live LLM providers
- `FEATURE_KILL_SWITCH` / `FEATURE_AUTO_TUNING` = true

## Preconditions

Gate 10E complete: C4 canary 100%, soak ≥24h, mock_router via canary PASS, kill/autotune OFF.

## Operator steps

1. `make gate10f-flip-router ARGS='--check'`
2. `make gate10f-flip-router ARGS='--dry-run'`
3. `make gate10f-flip-router ARGS='--apply'`
4. PR merge Blueprint change → **Render Sync** `saveiq-production`
5. `production_smoke.py --allow-active-canary --require-admin`
6. Confirm `/admin/router-status` → `active` + `mode=mock` (never `live`)

## Success criteria

| Check | Expected |
| --- | --- |
| Blueprint | `FEATURE_AI_ROUTER=true`, `AI_ROUTER_MODE=mock` |
| Kill / autotune | still `false` |
| Chinese LLM providers | still `false` |
| Smoke | pass with mock/active allowed |
| Router admin | mode=`mock` |

## Artifacts

- `scripts/gate10f_flip_router.py`
- `artifacts/gate10e_rollout_state.json` → `gate10f_router_flip`
- `docs/GATE_10E_ROLLOUT_REPORT.md` Gate 10F section
- RUNBOOK §3f
