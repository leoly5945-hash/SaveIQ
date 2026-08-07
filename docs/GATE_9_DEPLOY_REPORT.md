# Gate 9 Deploy & Smoke Report

Date: 2026-08-07  
`main` tip: `f0dab12`  
Blueprint: `saveiq-staging` (`render.yaml`)

## Verdict

| Step | Status | Notes |
| --- | --- | --- |
| PRs to `main` | PASS | [#1](https://github.com/leoly5945-hash/SaveIQ/pull/1), [#2](https://github.com/leoly5945-hash/SaveIQ/pull/2) merged |
| CI | PASS | Feature PR CI green after mypy fix; post-merge CI green |
| Container publish | PASS | Gate 9 images published to GHCR |
| Image pin in blueprint | PASS | Digests pinned in `render.yaml` via PR #2 |
| Staging live Gate 9 surfaces | PASS | OpenAPI exposes router/bandit/personalization/models/benchmark paths |
| Full `make staging-smoke` | PASS | Operator run: `staging_smoke=ok` (features remain off by design) |
| Public smoke probes | PASS | Health + Gate 6–9 public status endpoints respond as expected (features off) |

## Pull requests

1. **[#1 Add Gates 6B–9…](https://github.com/leoly5945-hash/SaveIQ/pull/1)**  
   - Source: `feature/gate-9-super-intelligence` (`829926e` + mypy fix `c07c2a9`)  
   - Merged as `c597022`
2. **[#2 Pin Gate 9 staging images](https://github.com/leoly5945-hash/SaveIQ/pull/2)**  
   - Pins immutable GHCR digests in `render.yaml`  
   - Merged as `f0dab12`

## Images

Pinned in `render.yaml` (from publish after PR #1 merge, run `31143900205`):

| Service | Digest |
| --- | --- |
| API | `ghcr.io/leoly5945-hash/saveiq-engine@sha256:9f6de983690a5b4a3c2dedf4076127cc8d1535c410c19795423d42c20ef2b1d1` |
| Web | `ghcr.io/leoly5945-hash/saveiq-web@sha256:7cf2997dc3e3378f1f9896e33bbf8e58d4f3f0cbe52466a8da71d0c533896a02` |

Note: merging the pin PR also re-ran Publish Containers (`31144037970`) and produced newer floating `:staging` tags. Staging Blueprint continues to use the **pinned** digests above.

## Staging endpoints (new / Gate 6–9)

Observed on live OpenAPI (`42` total paths). Gate-related paths present:

### Public / web-safe
- `GET /bandit/status`
- `GET /personalization/status`
- `GET /user/profile`
- `GET /user/recommendations`
- `POST /user/feedback`
- `POST /user/opt-out`
- Web proxies: `/api/bandit/status`, `/api/personalization/status`

### Admin (require `X-Admin-Token`)
- `GET /admin/router-status`
- `GET /admin/router/config`
- `GET /admin/router/metrics`
- `GET /admin/bandit/status`
- `GET /admin/bandit/metrics`
- `POST /admin/bandit/reset`
- `POST /admin/bandit/train`
- `POST /admin/bandit/switch_policy`
- `GET /admin/users/stats`
- `GET /admin/models/status`
- `GET /admin/benchmark/results`
- `POST /admin/benchmark/run`

## Public probe results (2026-08-07)

| Check | HTTP | Latency | Result |
| --- | ---: | ---: | --- |
| API `/health` | 200 | ~300–620 ms (p50 ~313 ms warm) | `status=ok` |
| Web `/api/health` | 200 | ~630 ms | `status=ok`; `X-Robots-Tag: noindex, nofollow` |
| `/bandit/status` | 200 | ~334 ms | `active=false`, `mode=disabled`, algorithm `linucb` |
| `/personalization/status` | 200 | ~917 ms | `feature_enabled=false` (safe default) |
| Web bandit proxy | 200 | ~892 ms | matches API |
| Web personalization proxy | 200 | ~383 ms | matches API |
| `/admin/router-status` (no token) | 401 | ~303 ms | auth required (expected) |
| `/admin/models/status` (no token) | 401 | ~612 ms | auth required (expected) |
| `/admin/benchmark/results` (no token) | 401 | ~295 ms | auth required (expected) |
| `/search?q=laptop` | 200 | ~725 ms | `count=0` (catalog empty until mock sync) |

Blueprint validation: `PYTHON=.venv/bin/python make staging-provision-validate` → `staging_provisioning_validation=ok`.

## Full smoke (PASS — operator run 2026-08-07)

```text
staging_smoke=ok
api_health=ok
web_health=ok
mock_sync=completed
llm_parser_status=active=intent-parser-v0 live_ready=False configured=False
ai_router_status=active=False mode=disabled live_ready=False
ai_router_metrics=cache_hits=0 cache_misses=0
bandit_status=enabled=False mode=disabled controls=False
bandit_public_status=enabled=False
personalization_status=enabled=False
user_profile_probe=skipped=personalization_disabled
admin_user_stats=users=0 events=0
admin_models_status=chinese=False
admin_benchmark_results=samples=40 policies=5
admin_summary=offers=6
api_search=count=2
api_recommendations=count=1 trace=33 rule=ruleset-2026-07-27-gate-4o parser=intent-parser-v0
recommendation_evaluation=passed=4 failed=0
click_analytics=total=42
recommendation_traces=total=34
```

Gate 6–9 endpoints are deployed and checked; advanced flags stay disabled (safe staging defaults).

## Safety observed on staging

Feature defaults remain off:
- Bandit: disabled / not controlling routing
- Personalization: `feature_enabled=false`
- Chinese LLM / neural / RLHF / Bayesian flags: not enabled for this probe

## Residual risks / follow-ups

1. Complete `make staging-smoke` with Render `ADMIN_API_TOKEN`.
2. If catalog is empty, run staging mock affiliate sync then re-check search/recommendations.
3. Optionally re-pin `render.yaml` to digests from publish run `31144037970` if you want Blueprint digests to match the latest `:staging` rebuild (code is already Gate 9).
4. Keep `bangiao.md` untracked; do not commit secrets.
