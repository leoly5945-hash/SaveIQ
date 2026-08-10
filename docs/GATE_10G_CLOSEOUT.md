# Gate 10G Closeout — live providers / Chinese LLM

**Status: COMPLETE** (verified 2026-08-10)

## Scope

Flip production from Gate 10F mock router to:

- `AI_ROUTER_MODE=live`
- `FEATURE_CHINESE_LLM_PROVIDERS=true`

Out of scope (still OFF):

- `FEATURE_KILL_SWITCH` / `FEATURE_AUTO_TUNING` = true
- Neural / RLHF policies
- Writing provider API keys into git (Render secrets only)

## Preconditions

- Gate 10E: C4 100%, soak ≥24h, mock_router PASS, kill/autotune OFF
- Gate 10F: global `FEATURE_AI_ROUTER=true` + `mode=mock` verified by smoke
- Chinese key in Render — **PASS** (`DEEPSEEK_API_KEY`)

## Operator steps (done)

1. `--check` — PASS  
2. `--evaluate` — PASS (`deepseek=true`, `ready_for_apply=true`)  
3. DeepSeek key set in Render  
4. Blueprint apply → PR [#25](https://github.com/leoly5945-hash/SaveIQ/pull/25) merged  
5. Render Sync `saveiq-production`  
6. Smoke PASS: `mode=live`, `chinese=True`, kill/autotune OFF  

## Success criteria

| Check | Expected | Result |
| --- | --- | --- |
| Router mode | `live` | **PASS** (`active=True mode=live`) |
| Chinese flag | `true` | **PASS** (`chinese=True`) |
| Kill / autotune | `false` | **PASS** |
| DeepSeek key | present | **PASS** |
| Smoke | ok with Gate 10G allow flags | **PASS** |
| Canary | 100% | **PASS** |

## Posture after Gate 10G

- Global AI router: **ON**, **live**
- Chinese LLM providers: **ON** (DeepSeek configured)
- Kill switch / auto-tune: **OFF**
- Canary: enabled 100%

## Rollback

Blueprint: `AI_ROUTER_MODE=mock`, `FEATURE_CHINESE_LLM_PROVIDERS=false` → Sync → Gate 10F smoke flags.

## Artifacts

- `scripts/gate10g_live_providers.py`
- `artifacts/gate10g_evaluation.json`
- RUNBOOK §3g
- PR #25
