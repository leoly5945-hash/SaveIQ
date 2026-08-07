# Production Runbook (Gate 10A)

Environment: **production** (`saveiq-production`)  
Blueprint: `render-production.yaml`  
Staging remains the experiment sandbox (`render.yaml`).

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

Change `numInstances` or plans in `render-production.yaml`, validate, Sync Blueprint. Prefer vertical plan upgrades before multi-instance until sticky sessions / cache strategy are reviewed (Gate 10C).

## 4. Monitoring and alerts

Gate 10B will formalize SLOs. For 10A, watch at minimum:

- Render service metrics: CPU, memory, instance health, deploy failures
- `/health` and `/api/health` uptime
- `GET /admin/rate-limit/status` (enabled, store=redis preferred)
- `GET /admin/router-status`, `/bandit/status`, `/personalization/status` — must stay inactive/disabled
- Application logs for 429 bursts, Redis disconnects, migration errors

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
- `docs/SECURITY.md` — secret and PII rules
- `docs/STAGING_RESOURCE_REGISTER.md` — staging only (do not mix secrets)
