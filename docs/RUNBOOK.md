# Production Runbook (Gate 10A / 10B / 10C / 10D)

Environment: **production** (`saveiq-production`)  
Blueprint: `render-production.yaml`  
Staging remains the experiment sandbox (`render.yaml`).
SLOs: `docs/SLOS.md` · Alert rules: `monitoring/alerts.yml`

## 1. Deploy procedure

Production services have `autoDeployTrigger: off`. Deploys are intentional.

1. Merge release changes to `main` and wait for CI + Publish Containers.
2. Copy immutable digests from the publish workflow logs into `render-production.yaml`:
   - `ghcr.io/<owner>/saveiq-engine@sha256:…`
   - `ghcr.io/<owner>/saveiq-web@sha256:…`
3. Validate:

   ```bash
   PYTHON=.venv/bin/python make production-provision-validate
   ```

4. Open a PR that only updates digests (or include with the release). Merge after review.
5. In Render → Blueprints → **saveiq-production** → Sync / Apply.
6. Confirm secrets exist and are **not** shared with staging:
   - `ADMIN_API_TOKEN`
   - Optional provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, Chinese keys) — leave unset until a later gate
7. Wait until `dealhunter-production-api` and `dealhunter-production-web` are healthy.
8. Run smoke:

   ```bash
   export ADMIN_API_TOKEN="..."   # from Render production env only
   PYTHON=.venv/bin/python make production-smoke
   ```

Helper (validation + operator checklist):

```bash
PYTHON=.venv/bin/python make deploy-production
```

## 2. Rollback procedure

Trigger rollback when: smoke fails, 5xx spike, latency spike, unexpected feature enablement, or security incident.

1. **Immediate:** In Render, redeploy the previous known-good image digests for API and web (or Sync an older `render-production.yaml` pin).
2. **Flags:** Confirm AI/bandit/personalization/Chinese/auto-tuning remain `false` in production env.
3. **Code:** If a bad commit reached `main`, revert via PR and re-pin digests after a green publish.
4. Re-run `make production-smoke`.
5. Record the incident and digest pair in `docs/DECISIONS.md` or the ops log.

Do **not** force-push `main` unless explicitly approved.

## 3. Scaling

| Resource | Gate 10A default | Scale when |
| --- | --- | --- |
| API / web `numInstances` | `1` (starter) | Sustained CPU/RAM >70% or p95 latency breach |
| Postgres | `basic-256mb` | Connection errors, storage pressure |
| Redis / Key Value | `starter` | Evictions hurting rate-limit/cache |

Change `numInstances` or plans in `render-production.yaml`, validate, Sync Blueprint. Prefer vertical plan upgrades before multi-instance; canary sticky assignment is Redis-backed (`CANARY_STICKY_SESSION`).

## 3b. Canary rollout (Gate 10C)

**Default:** `CANARY_ENABLED=false`, `CANARY_PERCENTAGE=0`. Global AI flags stay `false`.
Runtime overrides (no redeploy):

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/canary/status` | Current enabled / percentage / features / sticky |
| `POST /admin/canary/config` | Set `enabled`, `percentage` (0–100), `features`, `sticky_session` |
| `GET /admin/canary/stats` | Assignment counters + monitoring notes |

Features: `router`, `bandit`, `personalization`, `llm_cn`.
Assignment: sticky hash of `user_id` (or IP) per feature; Redis TTL 24h when sticky is on.
Prometheus label `canary=true|false|off` on HTTP/LLM/cost metrics for cohort comparison.

### Phases

| Phase | Percentage | Minimum soak |
| --- | --- | --- |
| C0 | 0% | baseline (canary off) |
| C1 | 1% | ≥ 24h |
| C2 | 5% | ≥ 24h |
| C3 | 25% | ≥ 24h |
| C4 | 100% | then consider global `FEATURE_*=true` |

Example advance to 1%:

```bash
curl -sS -X POST "$API_URL/admin/canary/config" \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"percentage":1,"features":["router","bandit","personalization","llm_cn"]}'
```

Prefer starting with `["router"]` only, then add bandit / personalization / `llm_cn` in later phases.

### Rollback criteria (immediate)

Rollback if **canary vs control** (Grafana panels) shows any of:

- Error rate (5xx) increase **> 1 absolute percentage point**
- Latency p95 increase **> 20%**
- Estimated LLM cost increase **> 50%** (when live providers are used)

Also rollback on smoke failure, unexpected provider spend, or security incident.

### Rollback procedure

```bash
curl -sS -X POST "$API_URL/admin/canary/config" \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled":false,"percentage":0}'
```

Confirm:

```bash
curl -sS "$API_URL/admin/canary/status" -H "X-Admin-Token: $ADMIN_API_TOKEN"
PYTHON=.venv/bin/python make production-smoke
```

Env kill-switch (requires Render Sync): set `CANARY_ENABLED=false` and `CANARY_PERCENTAGE=0`.
Runtime Redis override still wins until cleared — prefer admin POST above for instant disable.

### Monitoring during canary

- Grafana: Error rate / Latency p95 / LLM cost **canary vs control**
- `/admin/canary/stats` assignment counts
- Keep global feature flags false until C4 is stable

## 3c. A/B testing (Gate 10D)

**Default:** `FEATURE_ABTEST_ENABLED=false`, experiment not running.
Config file: `config/abtest.yaml` (control vs `treatment_a` router mock holdout).

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/abtest/status` | Feature flag, running, active experiment, stats |
| `POST /admin/abtest/start` | Enable + start (`{"experiment":"router_holdout_v1"}`) |
| `POST /admin/abtest/stop` | Stop assignment (kill switch) |
| `POST /admin/abtest/config` | Runtime tweaks / reload YAML |
| `GET /admin/abtest/significance` | Chi-square on conversion contingency |

Sticky assignment: `md5(experiment:user_id)` → Redis key `abtest:{experiment}:{user_id}` (TTL 30d).
Client headers: `X-User-ID` (preferred) or `X-Anonymous-User-Id`.
Response: `X-AB-Group`, `X-AB-Experiment`.
Prometheus label `ab_group` on HTTP/LLM metrics.

### Safe enablement order

1. Canary at a stable stage (e.g. C2) **or** canary off — do not stack risky live LLM + A/B without a plan.
2. Confirm smoke with A/B **off**.
3. `POST /admin/abtest/start` with `router_holdout_v1` (treatment uses **mock** router by default).
4. Monitor Grafana **ab_group** panels + `/admin/abtest/significance`.
5. Stop via `POST /admin/abtest/stop` or set `FEATURE_ABTEST_ENABLED=false` + Sync.

### Rollback

```bash
curl -sS -X POST "$API_URL/admin/abtest/stop" \
  -H "X-Admin-Token: $ADMIN_API_TOKEN"
```

## 3d. Kill switch + auto-tune (Gate 10E)

**Default:** `FEATURE_KILL_SWITCH=false`, `FEATURE_AUTO_TUNING=false`, `AUTO_TUNE_DRY_RUN=true`.
Canary auto-ramp is **off** by default (`AUTO_TUNE_CANARY_ENABLED=false`) so Gate 10C/10D ops are not overridden.

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/safety/status` | Env flags, runtime, hparams, window metrics, thresholds |
| `POST /admin/safety/config` | Runtime arm/disarm, `manual_override`, `dry_run`, canary auto-ramp |
| `POST /admin/safety/evaluate` | Run kill checks then auto-tune tick (`{"force_tune":true}` optional) |
| `POST /admin/safety/kill/trip` | Manual trip / drill (`force=true` bypasses override) |
| `POST /admin/safety/kill/disarm` | Clear trip state |
| `POST /admin/safety/autotune/apply` | Admin override epsilon/α/β/γ/cache TTL (within caps) |
| `POST /admin/safety/autotune/reset` | Reset hparams to env defaults |
| `GET /admin/safety/audit` | Recent change / trip log |

### Kill switch behavior

When armed and window metrics breach thresholds (error rate / latency p95 / cost per minute):

1. Mark `tripped` + reason
2. Stop A/B (`stop_abtest`)
3. Zero canary (`zero_canary`)
4. Disable auto-tune runtime
5. Reset bandit/cache hparams to safe env defaults

`manual_override=true` blocks automatic trip and auto-tune until cleared.

### Auto-tune behavior

Adjusts **within caps** only: epsilon, reward α/β/γ, router cache TTL.
Optional canary step (0–25%, step ≤5%) only if `auto_tune_canary_enabled` and **A/B is not running**.
Never flips neural / RLHF / Chinese / `BANDIT_POLICY` (human-only).
Default `dry_run=true` proposes + audits without applying.

### Staging drill (before production enable)

1. Staging: set env `FEATURE_KILL_SWITCH=true` (keep auto-tune dry-run).
2. `POST /admin/safety/kill/trip` with `{"reason":"drill"}` → confirm A/B stopped / canary zeroed.
3. `POST /admin/safety/kill/disarm`.
4. Enable `FEATURE_AUTO_TUNING=true` with `AUTO_TUNE_DRY_RUN=true`; `POST /admin/safety/evaluate`.
5. Review `/admin/safety/audit` before turning dry-run off.

### Emergency override

```bash
curl -sS -X POST "$API_URL/admin/safety/config" \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"manual_override":true,"auto_tune_enabled":false,"kill_switch_enabled":false}'
```

Or env kill: Sync Blueprint with `FEATURE_KILL_SWITCH=false` / `FEATURE_AUTO_TUNING=false`.

## 3e. Gate 10E rollout automation (staging drill → C3 → C4 → mock)

Script: `scripts/gate10e_rollout.py` · Make: `make gate10e-rollout ARGS='--phase …'`

**Prerequisite:** Staging must run a Gate 10E+ image (`/admin/safety/*` and `/admin/canary/*` in OpenAPI).
Production already has these after Gate 10E pin Sync. If staging OpenAPI lacks them, pin/Sync staging first.

**Tokens (never commit):**

```bash
export STAGING_ADMIN_TOKEN=...   # Render staging ADMIN_API_TOKEN
export PROD_ADMIN_TOKEN=...      # Render production ADMIN_API_TOKEN
```

**Phases (stop on first failure; soak clock in `artifacts/gate10e_rollout_state.json`):**

| Phase | What it does |
| --- | --- |
| `staging_drill` | Arm safety on **staging**, trip kill switch, verify canary→0 + A/B stop, evaluate dry-run, cleanup |
| `c3` | Prod canary **25%** (requires C2 + staging_drill; smoke; rollback on failure) |
| `soak_c3` | Assert ≥24h since C3 (no mutation) |
| `c4` | Prod canary **100%** after C3 soak |
| `soak_c4` | Assert ≥24h since C4 |
| `mock_router` | Ensure C4 + `router` feature (effective mock via canary; does **not** flip prod env flags) |
| `rollback` | Immediate prod canary `enabled=false,percentage=0` |
| `status` | Print state + live staging/prod snapshots |

```bash
# 1) Staging drill (required before C3)
.venv/bin/python scripts/gate10e_rollout.py --phase staging_drill

# 2) Advance to C3 (only if currently C2)
.venv/bin/python scripts/gate10e_rollout.py --phase c3

# 3) After ≥24h
.venv/bin/python scripts/gate10e_rollout.py --phase soak_c3
.venv/bin/python scripts/gate10e_rollout.py --phase c4

# 4) After ≥24h at C4
.venv/bin/python scripts/gate10e_rollout.py --phase soak_c4
.venv/bin/python scripts/gate10e_rollout.py --phase mock_router

# Emergency
.venv/bin/python scripts/gate10e_rollout.py --phase rollback
```

`--soak-seconds 60` is for local testing only. Production must use default **86400**.  
Script **refuses** to continue if production `FEATURE_KILL_SWITCH` / `FEATURE_AUTO_TUNING` env are true.

### Background auto-rollout daemon

Script: `scripts/gate10e_auto_rollout.py` (polls soak monitor, advances phases, writes report).

```bash
export PROD_ADMIN_TOKEN=...

# Check remaining soak
.venv/bin/python scripts/gate10e_auto_rollout.py --status

# Run in background (no --force; rollback on breach)
nohup .venv/bin/python scripts/gate10e_auto_rollout.py --daemon \
  > artifacts/gate10e_auto_rollout.log 2>&1 &
echo $! > artifacts/gate10e_auto_rollout.pid

# After C4 soak, auto-run mock_router (optional)
# add --auto-mock

# Stop
kill "$(cat artifacts/gate10e_auto_rollout.pid)"
```

Artifacts: `artifacts/gate10e_auto_rollout.log`, `artifacts/gate10e_auto_rollout_state.json`,  
report: `docs/GATE_10E_ROLLOUT_REPORT.md`.

## 3f. Gate 10F — global `FEATURE_AI_ROUTER` flip (mock only)

Script: `scripts/gate10f_flip_router.py` · Make: `make gate10f-flip-router ARGS='…'`

**Goal:** Flip production Blueprint `FEATURE_AI_ROUTER=false` → `true` with `AI_ROUTER_MODE=mock`.  
Does **not** enable live LLM providers, kill switch, or auto-tuning.

**Prerequisites (Gate 10E complete):**

- `artifacts/gate10e_rollout_state.json`: `c4_percentage=100`, C4 soak ≥24h, `mock_router_ready_at` set
- Live canary enabled at **100%** with `router` feature
- Production kill/autotune env **OFF**, kill not tripped
- Router mode is **not** already `live`

```bash
export PROD_ADMIN_TOKEN=...   # for live prerequisite checks

# 1) Verify prerequisites (state + live API)
make gate10f-flip-router ARGS='--check'

# 2) Preview Blueprint edits (no write)
make gate10f-flip-router ARGS='--dry-run'

# 3) Write local Blueprint + update state/report
make gate10f-flip-router ARGS='--apply'

# 4) Commit → PR → merge → Render Dashboard → saveiq-production → Sync

# 5) Post-Sync smoke (mock/active allowed; live still fails)
ADMIN_API_TOKEN=... .venv/bin/python scripts/production_smoke.py \
  --allow-active-canary --require-admin

# 6) Confirm
curl -sH "X-Admin-Token: $PROD_ADMIN_TOKEN" \
  "$API_URL/admin/router-status"   # expect active + mode=mock
```

State-only check (no live API): add `--skip-live-checks` (not recommended for apply).  
`--force` skips all prerequisite checks — ops emergency only.

**Rollback:** set Blueprint `FEATURE_AI_ROUTER=false` and `AI_ROUTER_MODE=disabled` (or previous values), Sync Render, re-smoke.

## 4. Monitoring and alerts

### Signals

- Render service metrics: CPU, memory, instance health, deploy failures
- `/health` and `/api/health` uptime
- `GET /metrics` — Prometheus SLIs (optional `X-Metrics-Token` if `METRICS_TOKEN` set)
- Structured JSON logs on API stdout (`request_id`, `duration_ms`, `status_code`)
- `GET /admin/rate-limit/status` (enabled, store=redis preferred)
- `GET /admin/router-status`, `/bandit/status`, `/personalization/status` — must stay inactive until canary
- Grafana: import `monitoring/grafana-dashboard.json`
- Prometheus scrape example: `monitoring/prometheus.yml`
- Alertmanager Slack/email template: `monitoring/alertmanager.yml` (set `SLACK_WEBHOOK_URL` outside git)

### Alert playbooks

#### HighErrorRate {#higherrorrate}

- **Meaning:** 5xx ratio exceeded threshold.
- **Check:** Render API logs for Tracebacks; `/metrics` `http_requests_total{status_code="5.."}`; recent deploy.
- **Actions:** Rollback image digest if deploy-correlated; disable AI flags; verify Postgres/Redis; scale if OOM/CPU.

#### HighLatency {#highlatency}

- **Meaning:** p95 on `/search` or `/recommendations` > 1.5s sustained.
- **Check:** DB slow queries / connection pool; Redis latency; cold start after idle; LLM provider if flags on.
- **Actions:** Warm instance; scale `numInstances`/plan; disable live LLM; fall back to rule-based path.

#### LLMProviderDown {#llmproviderdown}

- **Meaning:** Provider error rate > 10% while AI router is live.
- **Check:** `/admin/router-status`, `/admin/router/metrics`; provider status pages; API keys validity (never paste keys).
- **Actions:** Set `FEATURE_AI_ROUTER=false` or `AI_ROUTER_MODE=disabled`; switch fallback provider; rotate key if auth errors.

#### HighCost {#highcost}

- **Meaning:** Estimated LLM spend > $10/hour.
- **Check:** `llm_cost_usd_total` by provider; cache hit rate; unexpected traffic.
- **Actions:** Disable live providers; tighten cache TTL; reduce traffic / rate limits; investigate abuse (429s).

#### CacheMissHigh {#cachemisshigh}

- **Meaning:** Router cache hit rate < 50% with meaningful traffic.
- **Check:** Redis health; `AI_ROUTER_CACHE_ENABLED`; TTL too low; key churn from unique queries.
- **Actions:** Fix Redis; raise TTL carefully; confirm cache enabled.

#### BanditRegretHigh {#banditregrethigh}

- **Meaning:** Regret counter rising quickly (when bandit active).
- **Check:** `/admin/bandit/status`, policy, sample counts; confirm not controlling routing unexpectedly.
- **Actions:** Set `BANDIT_ROUTER_MODE=logging` or `disabled`; keep `FEATURE_BANDIT_ROUTER=false` until Gate 10C/D.

## 5. Common troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| API boot loop | Bad `DATABASE_URL` / migration | Check Render logs; confirm Postgres available; run migrations via release process |
| Rate limit 429 for clients | Expected under load or limit too low | Inspect `/admin/rate-limit/status`; adjust `RATE_LIMIT_*` env with PR + Sync |
| Rate limit store=`memory` | Redis unreachable | Fix `REDIS_URL` / Key Value service; restart API |
| CORS errors | Wrong `API_CORS_ORIGINS` | Must match production web origin only |
| Smoke fails on noindex | Missing `PRODUCTION_NOINDEX=true` | Set on web service; redeploy |
| Feature unexpectedly on | Env drift | Diff Render env vs `render-production.yaml`; reset flags to `false` |
| LLM provider errors | Key present + flag on | Disable flags; rotate/remove keys if leaked |

## 6. Emergency contacts

| Role | Contact |
| --- | --- |
| On-call / deploy owner | TBD |
| Product owner | TBD |
| Security escalation | TBD |

Keep phone/email lists outside git if sensitive. Update this table when the on-call rota exists.

## Related docs

- `docs/GATE_10_PLAN.md` — full rollout plan (10A–10F)
- `docs/GATE_10A_CLOSEOUT.md` — Gate 10A evidence
- `docs/GATE_10B_CLOSEOUT.md` — Gate 10B evidence
- `docs/GATE_10C_CLOSEOUT.md` — Gate 10C evidence
- `docs/GATE_10D_CLOSEOUT.md` — Gate 10D evidence
- `docs/GATE_10E_CLOSEOUT.md` — Gate 10E evidence
- `docs/SLOS.md` — SLOs / SLIs
- `docs/SECURITY.md` — secret and PII rules
- `docs/STAGING_RESOURCE_REGISTER.md` — staging only (do not mix secrets)
