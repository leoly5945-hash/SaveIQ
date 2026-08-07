# Gate 10 Plan — Production Rollout

Date: 2026-08-07  
Depends on: Gates 6B–9 merged, staging smoke green (`staging_smoke=ok`), feature defaults off  
Goal: Controlled production enablement with canary traffic, monitoring, A/B comparison, and safe
auto-adjustment — without turning on live AI/affiliate behavior until each sub-gate passes.

## Non-goals (still deferred)

- Web scraping or unapproved affiliate scraping
- Full autonomous shopping agent
- Enabling Chinese LLM / neural / RLHF in production without canary evidence
- Storing raw prompts, model responses, PII, or secrets in traces

## Success criteria

1. Production Blueprint exists separately from staging (`saveiq-production` or equivalent).
2. Canary serves ≤5% traffic with automatic rollback on SLO breach.
3. Router/bandit/personalization can be enabled independently behind flags.
4. A/B (or bandit logging-first) proves no regression vs rule-based baseline on primary metrics.
5. Auto-adjust only tunes safe knobs (cache TTL, epsilon, traffic %, provider weight) within hard caps.
6. Production smoke + on-call runbook documented; secrets only in Render/secret store.

## Rollout phases

### Gate 10A — Production foundation

- Add production Render Blueprint (paid Postgres/Redis; no free-tier expiry assumptions).
- Pin immutable GHCR digests; separate `ADMIN_API_TOKEN` and provider keys.
- Production health checks, noindex until public launch decision, CORS allowlist.
- Rate limits on public search/recommendation/user endpoints.
- Dependency scanning in CI (required before first production traffic).
- Runbook: deploy, migrate, rollback image digest, rotate admin token.

**Status:** Implemented in-repo (`render-production.yaml`, rate limits, CI scans, `docs/RUNBOOK.md`).  
Live Render apply + `production_smoke=ok` remain operator steps after billing/Blueprint Sync.  
**Closeout:** `docs/GATE_10A_CLOSEOUT.md`

**Exit:** production `/health` + web health green; staging remains the experiment sandbox.

### Gate 10B — Observability & SLOs

Instrument and alert on:

| Signal | Initial SLO / alert |
| --- | --- |
| API availability | 99.5% rolling 24h |
| p95 latency `/search`, `/recommendations` | < 1.5s warm (tune after baseline) |
| Error rate 5xx | < 1% |
| Router fallback rate | tracked; alert if spike vs baseline |
| LLM/provider error rate | < 5% of live calls when enabled |
| Cost per 1k recommendations | budget cap + daily alert |
| Bandit log write failures | alert on sustained errors |

Dashboards: router cache hit rate, provider mix, bandit policy, personalization opt-out rate,
benchmark sample growth. Admin metrics endpoints already exist; wire to Render/logs or metrics sink.

**Exit:** alerts fire in a staged drill; on-call knows rollback switches.

### Gate 10C — Canary deploy

Traffic split (edge or app-level sticky anonymous id):

| Stage | Canary % | Duration | Features |
| --- | ---: | --- | --- |
| C0 | 0% | deploy only | all AI flags off |
| C1 | 1% | ≥24h | logging-only bandit optional |
| C2 | 5% | ≥48h | AI router mock/cache path or single live provider if approved |
| C3 | 25% | ≥72h | expand only if C2 gates pass |
| C4 | 100% | — | promote digests + flags |

**Hard rollback triggers (any):** 5xx >2x baseline, p95 >2x baseline, cost > budget, provider
timeout storm, data/PII incident, smoke failure after deploy.

Rollback actions (ordered): set canary % → 0; disable feature flags; redeploy last known-good digest.

**Exit:** C2 completes without rollback; promote decision recorded in `docs/DECISIONS.md`.

### Gate 10D — A/B and policy comparison

Holdout design:

- **Control:** rule-based recommendations + deterministic parser (current staging baseline).
- **Treatment A:** AI router enabled (approved providers only), bandit logging-first.
- **Treatment B (later):** bandit `controls_routing` or personalization boost — only after A wins or ties.

Primary metrics: helpful rate, click-through on affiliate links (mock→real when partners exist),
fallback rate, latency, cost. Secondary: diversity, opt-out rate, complaint rate.

Use offline benchmark (`/admin/benchmark/*`) + online holdout. Prefer IPS/DR when propensity
scores are trusted; until then, randomized sticky assignment + CUPED if volume allows.

**Exit:** documented lift or “no worse than control” with confidence interval; no silent policy flip.

### Gate 10E — Auto-adjustment (guardrailed)

Allow automated tuning only inside caps:

| Knob | Auto? | Caps |
| --- | --- | --- |
| Canary % up/down | yes | 0–25% until human promote; step ≤5% |
| Router cache TTL | yes | min/max bounds |
| Bandit epsilon / exploration | yes | Bayesian tuner offline → propose; human or strict cap apply |
| Provider weight / disable unhealthy provider | yes | never remove last healthy fallback |
| Enable neural / RLHF / Chinese providers | **no** | human-only flags |
| `BANDIT_POLICY` switch | **no** unless dry-run + admin ack |

Auto-adjust must log every change with reason, previous value, and metric window. Kill switch:
`FEATURE_AUTO_TUNING=false` default until 10E exit.

**Exit:** 7 days of bounded auto-adjust with no safety incident; kill switch tested.

### Gate 10F — Production enablement checklist

Before any live provider key in production:

- [ ] Partner/affiliate ToS and credential vault reviewed
- [ ] PII policy: anonymous opaque ids only; retention limits enforced
- [ ] Trace/feedback retention jobs scheduled
- [ ] Cost budget and provider rate limits set
- [ ] Canary + rollback drill completed
- [ ] Production smoke script (`make production-smoke` or env-parameterized staging smoke)
- [ ] Security review of admin surface and CORS
- [ ] Incident runbook linked from README

## Suggested flag sequence (production)

Defaults remain **off**. Enable in order, each after canary evidence:

1. Observability only (no behavior change)
2. `FEATURE_BANDIT_ROUTER` logging-first (no routing control)
3. `FEATURE_AI_ROUTER` with mock or single approved provider + cache
4. Personalization read-path (opt-out honored)
5. Bandit controls routing (small epsilon)
6. Chinese providers / neural / RLHF — **optional**, after Gate 9 benchmark + cost review

## Deliverables

| Artifact | Owner |
| --- | --- |
| `render.production.yaml` (or Blueprint env) | platform |
| `docs/GATE_10_CLOSEOUT.md` per sub-gate | eng |
| Production smoke + alert playbooks | eng |
| Decision log entries for canary promote | eng + product |
| Cost budget sheet (not in git secrets) | eng |

## Risks

- Free staging Redis/Postgres semantics differ from production — validate persistence and bandit logs.
- Enabling live LLMs without cache/budget controls can spike cost in hours.
- Bandit control without enough traffic causes unstable arms — keep logging-first until sample threshold.
- Auto-tuning without caps can oscillate; require hysteresis and cooldown.

## Immediate next implementation slice (10A)

1. Draft production Blueprint from `render.yaml` with paid plans and secret sync notes.
2. Parameterize smoke script for `API_URL` / `WEB_URL` / `ADMIN_API_TOKEN`.
3. Add CI dependency scanning job (fail on high severity).
4. Document rollback digest pin procedure in README / runbook.
5. Baseline latency/error metrics from staging for one week before C1.
