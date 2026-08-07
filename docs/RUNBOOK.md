# Production Runbook (Gate 10A / 10B / 10C)

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
- `docs/SLOS.md` — SLOs / SLIs
- `docs/SECURITY.md` — secret and PII rules
- `docs/STAGING_RESOURCE_REGISTER.md` — staging only (do not mix secrets)
