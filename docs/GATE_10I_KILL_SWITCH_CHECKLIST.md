# Gate 10I: Kill Switch Enablement Checklist

Generated: 2026-08-13  
Updated: 2026-08-24  
Status: **ENABLEMENT COMPLETE** — Blueprint `FEATURE_KILL_SWITCH=true` (staging + production). 10I image live. Runtime armed, **not tripped**. Auto-tune stays **OFF** (Gate 10J).

API image pin (PR #35 code, Publish Containers run `32706540315`):

`ghcr.io/leoly5945-hash/saveiq-engine@sha256:e0ed93821f953537d2b4a3c122b644aeecf03e8074e9111d622d4635667a7cd8`

Web digest **unchanged**. `FEATURE_AUTO_TUNING` remains `false`.

## Scope

Arm `FEATURE_KILL_SWITCH=true` so operators can stop the AI router on breach or
manual trip. When tripped (10I image), the router falls back to the deterministic parser
(`request_router_active=false`). `FEATURE_AUTO_TUNING` remains `false`.

Do **not** disable `FEATURE_AI_ROUTER` for this gate. Surgical rollback is
disarm + Blueprint `FEATURE_KILL_SWITCH=false`.

## API (auth: `X-Admin-Token`)

Existing Gate 10E surfaces remain the source of truth:

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/safety/status` | Env + runtime + thresholds + window |
| `POST /admin/safety/kill/trip` | Manual trip |
| `POST /admin/safety/kill/disarm` | Clear trip |

Gate 10I aliases (same service, router-fallback fields) — **on the pinned 10I image**:

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/kill-switch/status` | `env_flag`, `armed`, `tripped`, `router_fallback`, `request_router_active` |
| `POST /admin/kill-switch/enable` | Arm runtime overlay; default `trip=true` (emergency stop) |
| `POST /admin/kill-switch/disable` | Disarm trip; `unarm=true` also clears runtime arm |

Live OpenAPI includes `/admin/kill-switch/*` after PR #36 pin + Manual Sync (2026-08-24). `/admin/safety/kill/*` remains valid.

`FEATURE_KILL_SWITCH` itself is a Render Blueprint env flag. The admin API
cannot mutate process env; durable enablement is Sync. Runtime overlay
(`kill_switch_enabled`) is what enable/disable arm.

## Preconditions

- [x] Gate 10H production Neural n100 + RLHF soak PASS (2026-08-23)
- [x] Kill switch **ON** in Blueprint (`true`); **not tripped**
- [x] Auto-tune still OFF
- [x] `/admin/safety/status` thresholds reviewed (error rate, latency p95, cost)
- [x] Staging + prod `ADMIN_API_TOKEN` available as `STAGING_ADMIN_TOKEN` / `PROD_ADMIN_TOKEN`

## Enablement

Script: `scripts/gate10i_kill_switch.py` · Make: `make gate10i-kill-switch ARGS='…'`  
Flag PR: https://github.com/leoly5945-hash/SaveIQ/pull/35 (merged 2026-08-24)

- [x] Staging Blueprint `FEATURE_KILL_SWITCH=true` (autotune false)
- [x] Staging drill PASS 2026-08-24 (`legacy=True` on pre-10I image; canary seeded 5% → 0; restore; audit)
- [x] Production Blueprint `FEATURE_KILL_SWITCH=true` (autotune false)
- [x] `prod-verify --assume-synced` PASS on **10I image** 2026-08-24 (`env_flag=true`, `armed=true`, `tripped=false`, router live; **no** `pre-10I` WARN)
- [x] `monitor --target prod` PASS (`http_5xx=0`) — re-run after image pin if desired
- [x] Pin 10I API digest (PR #36) + Render Manual Sync staging (`saveiq`) **and** production (`saveiq-production`)
- [x] OpenAPI includes `/admin/kill-switch/status`
- [x] Prod-drill **PASS** 2026-08-25 (`--stage prod-drill --confirm-trip`): trip → canary 100→0 + router fallback confirmed → immediate disarm → canary restored to 100; 4 audit events

```bash
export STAGING_ADMIN_TOKEN=...
export PROD_ADMIN_TOKEN=...

make gate10i-kill-switch ARGS='--stage prod-verify --assume-synced'
make gate10i-kill-switch ARGS='--stage monitor --target prod'
```

If `prod-verify` shows `env_flag=true` but `armed=false` (stale Redis overlay):

```bash
curl -sS -X POST "$API_URL/admin/kill-switch/enable" \
  -H "X-Admin-Token: $PROD_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"gate10i_arm","trip":false}'
```

## Expected trip behavior (10I image)

1. Mark `tripped` + reason; increment `kill_switch_trips_total`
2. Stop A/B, zero canary, disable auto-tune runtime, reset hparams
3. **AI router fallback** (`fallback_router`) — searches use the old parser
4. Gauges: `kill_switch_armed`, `kill_switch_tripped`

Trip on this image zeros canary / stops A/B **and** falls the AI router back to the parser (`request_router_active=false`).

`manual_override=true` blocks automatic trip until cleared. `force=true` still trips.

## Rollback

```bash
make gate10i-kill-switch ARGS='--stage rollback --target prod --confirm-rollback'
# → Sync Blueprint FEATURE_KILL_SWITCH=false
# FEATURE_AI_ROUTER / neural / RLHF are not touched
```

Emergency (no Blueprint wait):

```bash
curl -sS -X POST "$API_URL/admin/kill-switch/disable" \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"clear_window":true,"unarm":true}'
```

Or 10E equivalent: `POST /admin/safety/kill/disarm`.

## Out of scope

- `FEATURE_AUTO_TUNING` (Gate 10J) — **do not enable in this pin PR**
- Auto-flipping neural / RLHF / `BANDIT_POLICY` (human-only forever)
- Disabling `FEATURE_AI_ROUTER`
- Affiliate modules (`src/affiliate`, `src/router`)

## Sign-off

- [x] Staging drill PASS (trip → canary 0 → disarm → restore; image was pre-10I)
- [x] Production env `FEATURE_KILL_SWITCH=true`, autotune false, not tripped
- [x] Monitor PASS (`/metrics` HTTP 5xx)
- [x] 10I API image live (OpenAPI `/admin/kill-switch/*`) after PR #36 Sync; `prod-verify` 2026-08-24T08:53Z PASS, no `pre-10I` WARN
- [x] Prod drill **PASS** 2026-08-25 (canary 100→0→100, router fallback confirmed, trip cleared, 4 audit events)

## References

- `lamviec.md` — operator handover
- `docs/GATE_10H_NEURAL_RLHF_CHECKLIST.md`
- `docs/GATE_10E_CLOSEOUT.md` (human-only flag rule)
- `docs/RUNBOOK.md` §3d / §3i
- Admin: `/admin/kill-switch/*`, `/admin/safety/*`
