# Gate 10A Closeout — Production Blueprint & Runbook

Date: 2026-08-07  
Branch: `feature/gate-10a-production-foundation`

## Summary

Gate 10A adds a **separate production Blueprint**, immutable image pins, API rate limiting,
CI dependency scanning, an operator runbook, and a production smoke script. All AI / bandit /
personalization / Chinese / auto-tuning flags remain **off** in production.

## Delivered

| Item | Location |
| --- | --- |
| Production Blueprint (`saveiq-production`) | `render-production.yaml` |
| Paid plans + `numInstances` + `autoDeployTrigger: off` | API/web/redis/postgres |
| Digest pins (Gate 9 verified images) | engine `9f6de983…`, web `7cf2997d…` |
| Rate limiting (Redis + memory fallback) | `app/services/rate_limit.py`, middleware |
| Admin status | `GET /admin/rate-limit/status` |
| Env knobs | `RATE_LIMIT_ENABLED`, `RATE_LIMIT_*_PER_MINUTE` |
| CI dependency scan | `.github/workflows/ci.yml` job `security` |
| Container Trivy scan | `.github/workflows/container-publish.yml` |
| Local scan script | `scripts/security_scan.sh` |
| Deploy helper | `scripts/deploy_production.sh` |
| Production smoke | `scripts/production_smoke.py` |
| Runbook | `docs/RUNBOOK.md` |
| Blueprint validation | `scripts/validate_render_blueprint.py --profile production` |

## Safety defaults (production)

- `FEATURE_AI_ROUTER=false`, `FEATURE_BANDIT_ROUTER=false`, `FEATURE_PERSONALIZATION=false`
- `FEATURE_CHINESE_LLM_PROVIDERS=false`, neural/RLHF/embedding/Bayesian/auto-tuning `false`
- `RATE_LIMIT_ENABLED=true` (100 / 1000 / 50 per minute for public / auth / admin)
- `PRODUCTION_NOINDEX=true` until public launch
- Secrets via `sync: false` only — never in git

## Validation

```bash
PYTHON=.venv/bin/python make production-provision-validate
PYTHON=.venv/bin/python make staging-provision-validate
# plus standard lint/type/test/build
```

Live production apply is **operator-driven** (billing + Blueprint Sync). Smoke against live
production hosts runs after first apply:

```bash
ADMIN_API_TOKEN=... PYTHON=.venv/bin/python make production-smoke
```

## Exit criteria

- [x] Production Blueprint exists and validates locally
- [x] Digests pinned (immutable)
- [x] Rate limits implemented and tested
- [x] Dependency scanning in CI
- [x] Runbook documented
- [x] Blueprint applied in Render workspace (`saveiq-production`)
- [x] Live `production_smoke=ok` after first apply (2026-08-07)

### Live smoke evidence (2026-08-07)

```text
production_smoke=ok
api_health=ok
web_health=ok
production_noindex=noindex, nofollow
bandit_status=active=False mode=disabled
personalization_status=enabled=False
api_search=count=0
ai_router_status=active=False mode=disabled
admin_models_status=chinese=False
rate_limit_status=enabled=True public=100 store=redis
```

Notes: `api_search=count=0` is expected on a fresh production DB (no mock seed). AI/bandit/personalization remain off; rate limit uses Redis.

## Follow-ups (Gate 10B+)

- Observability / SLO alerts
- Canary traffic split
- Re-pin digests on each production release
- Parameterize production hostnames if custom domains are added
