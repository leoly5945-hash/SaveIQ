# Gate 10G Closeout — live providers / Chinese LLM

**Status: BLUEPRINT UPDATED** (awaiting PR merge + Render Sync)

## Scope

Flip production from Gate 10F mock router to:

- `AI_ROUTER_MODE=live`
- `FEATURE_CHINESE_LLM_PROVIDERS=true`

Out of scope:

- `FEATURE_KILL_SWITCH` / `FEATURE_AUTO_TUNING` = true
- Neural / RLHF policies
- Writing provider API keys into git (Render secrets only)

## Preconditions

- Gate 10E: C4 100%, soak ≥24h, mock_router PASS, kill/autotune OFF
- Gate 10F: global `FEATURE_AI_ROUTER=true` + `mode=mock` verified by smoke
- At least one Chinese key present in Render — **PASS** (`DEEPSEEK_API_KEY`)

## Operator steps

1. `make gate10g-live-providers ARGS='--check'` — PASS
2. `make gate10g-live-providers ARGS='--evaluate'` — PASS (`deepseek=true`)
3. Provider keys in Render — DEEPSEEK set
4. `--dry-run` / `--apply` — Blueprint updated locally
5. PR merge → Render Sync — **pending**
6. Smoke with `--allow-live-router --allow-chinese-providers --allow-active-canary --require-admin`
7. Confirm `/admin/router-status` → `mode=live`, chinese enabled

## Success criteria

| Check | Expected | Status |
| --- | --- | --- |
| Router mode | `live` | Blueprint set; await Sync |
| Chinese flag | `true` | Blueprint set; await Sync |
| Kill / autotune | `false` | unchanged |
| DeepSeek key | present | PASS (evaluate) |
| Smoke | pass with Gate 10G allow flags | pending Sync |

## Rollback

Blueprint: `AI_ROUTER_MODE=mock`, `FEATURE_CHINESE_LLM_PROVIDERS=false` → Sync → Gate 10F smoke flags.

## Artifacts

- `scripts/gate10g_live_providers.py`
- `artifacts/gate10g_evaluation.json`
- RUNBOOK §3g
