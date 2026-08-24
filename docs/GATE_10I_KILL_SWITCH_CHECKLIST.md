# Gate 10I: Kill Switch Enablement Checklist

Generated: 2026-08-13  
Updated: 2026-08-23  
Status: **IMPLEMENTED (code)** — Blueprint still `FEATURE_KILL_SWITCH=false`. Run script stages to enable. Auto-tune stays **OFF** (Gate 10J).

## Scope

Arm `FEATURE_KILL_SWITCH=true` so operators can stop the AI router on breach or
manual trip. When tripped, the router falls back to the deterministic parser
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

Gate 10I aliases (same service, router-fallback fields):

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/kill-switch/status` | `env_flag`, `armed`, `tripped`, `router_fallback`, `request_router_active` |
| `POST /admin/kill-switch/enable` | Arm runtime overlay; default `trip=true` (emergency stop) |
| `POST /admin/kill-switch/disable` | Disarm trip; `unarm=true` also clears runtime arm |

`FEATURE_KILL_SWITCH` itself is a Render Blueprint env flag. The admin API
cannot mutate process env; durable enablement is Sync. Runtime overlay
(`kill_switch_enabled`) is what enable/disable arm.

## Preconditions

- [x] Gate 10H production Neural n100 + RLHF soak PASS (2026-08-23)
- [ ] Kill switch still OFF in Blueprint (`false`); not tripped
- [ ] Auto-tune still OFF
- [ ] `/admin/safety/status` thresholds reviewed (error rate, latency p95, cost)
- [ ] Staging + prod `ADMIN_API_TOKEN` available as `STAGING_ADMIN_TOKEN` / `PROD_ADMIN_TOKEN`

## Enablement

Script: `scripts/gate10i_kill_switch.py` · Make: `make gate10i-kill-switch ARGS='…'`

```bash
export STAGING_ADMIN_TOKEN=...
export PROD_ADMIN_TOKEN=...

make gate10i-kill-switch ARGS='--stage check'
make gate10i-kill-switch ARGS='--stage staging-blueprint --dry-run'
make gate10i-kill-switch ARGS='--stage staging-blueprint --confirm-kill'
# → commit/PR or Sync staging Blueprint
make gate10i-kill-switch ARGS='--stage staging-sync'
make gate10i-kill-switch ARGS='--stage staging-drill --assume-synced --confirm-trip'

make gate10i-kill-switch ARGS='--stage prod-blueprint --dry-run'
make gate10i-kill-switch ARGS='--stage prod-blueprint --confirm-kill'
# → PR + Sync production. Then CI/make production-provision-validate needs --allow-kill-switch
make gate10i-kill-switch ARGS='--stage prod-sync'
make gate10i-kill-switch ARGS='--stage prod-verify --assume-synced'
make gate10i-kill-switch ARGS='--stage monitor --target prod'

# Optional production trip drill (zeros canary, forces parser fallback, then restores):
make gate10i-kill-switch ARGS='--stage prod-drill --confirm-trip'
```

If `prod-verify` shows `env_flag=true` but `armed=false` (stale Redis overlay):

```bash
curl -sS -X POST "$API_URL/admin/kill-switch/enable" \
  -H "X-Admin-Token: $PROD_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"gate10i_arm","trip":false}'
```

## Expected trip behavior

1. Mark `tripped` + reason; increment `kill_switch_trips_total`
2. Stop A/B, zero canary, disable auto-tune runtime, reset hparams
3. **AI router fallback** (`fallback_router`) — searches use the old parser
4. Gauges: `kill_switch_armed`, `kill_switch_tripped`

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

## Out of scope

- `FEATURE_AUTO_TUNING` (Gate 10J)
- Auto-flipping neural / RLHF / `BANDIT_POLICY` (human-only forever)
- Disabling `FEATURE_AI_ROUTER`

## Sign-off

- [ ] Staging drill PASS (trip → router fallback → disarm → canary restored)
- [ ] Production env `FEATURE_KILL_SWITCH=true`, autotune false, not tripped
- [ ] Monitor PASS (`/metrics` HTTP 5xx, `/admin/kill-switch/status`)
- [ ] Optional prod drill PASS (or explicitly deferred)

## References

- `docs/GATE_10H_NEURAL_RLHF_CHECKLIST.md`
- `docs/GATE_10E_CLOSEOUT.md` (human-only flag rule)
- `docs/RUNBOOK.md` §3d / §3i
- Admin: `/admin/kill-switch/*`, `/admin/safety/*`
