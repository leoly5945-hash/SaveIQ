# DealHunter AI Affiliate Platform

DealHunter is an AI-assisted affiliate deal discovery platform. This repository currently contains a
modular monolith foundation with a Next.js frontend, FastAPI backend, PostgreSQL with pgvector, Redis,
Alembic migrations, an affiliate domain model, a deterministic Canadian mock provider, and a mock
ingestion pipeline.

## Repository Layout

```text
apps/
  api/   FastAPI backend, SQLAlchemy models, provider adapters, ingestion, migrations
  web/   Next.js frontend
docs/    Product, architecture, data model, and API documentation
infra/   Local infrastructure initialization
```

## Local Setup

1. Copy environment defaults:

   ```bash
   cp .env.example .env
   ```

2. Start local infrastructure:

   ```bash
   docker compose up postgres redis
   ```

3. Install backend dependencies:

   ```bash
   cd apps/api
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -e ".[dev]"
   alembic upgrade head
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. Install frontend dependencies and run Next.js:

   ```bash
   npm install
   npm run dev:web
   ```

5. Open:

   - Frontend: <http://localhost:3000>
   - Frontend health: <http://localhost:3000/api/health>
   - Backend health: <http://localhost:8000/health>
   - Backend OpenAPI: <http://localhost:8000/docs>

## Mock Affiliate Sync

Run the deterministic mock provider ingestion:

```bash
curl -X POST http://localhost:8000/admin/affiliate/sync/mock \
  -H "X-Admin-Token: dev-admin-token"
```

Useful protected admin views:

```bash
curl http://localhost:8000/admin/affiliate/products -H "X-Admin-Token: dev-admin-token"
curl http://localhost:8000/admin/affiliate/offers -H "X-Admin-Token: dev-admin-token"
curl http://localhost:8000/admin/affiliate/price-history -H "X-Admin-Token: dev-admin-token"
curl http://localhost:8000/admin/affiliate/sync/jobs -H "X-Admin-Token: dev-admin-token"
```

## Mock Recommendations

Gate 4A exposes a deterministic recommendation skeleton. It parses simple shopping intent, retrieves
stored mock offers, and returns an inline evaluation trace without calling an LLM:

```bash
curl -X POST http://localhost:8000/recommendations \
  -H "Content-Type: application/json" \
  -d '{"intent":"Find fresh wireless earbuds with a coupon","limit":3}'
```

Gate 4B adds offline evaluation fixtures for the recommendation skeleton:

```bash
PYTHON=.venv/bin/python make recommendation-eval
```

The evaluator seeds a temporary in-memory database with the deterministic mock provider and checks
expected intent parsing, retrieval, ranking, first result, and trace guardrails.

Gate 4C persists each recommendation trace for staging audit. The API returns `trace_event_id`, and
admins can inspect recent traces through `GET /admin/affiliate/recommendation-traces` or the web
proxy `POST /api/admin/recommendation-traces`.

Gate 4D adds a staging UI trace viewer. Paste the admin token into the admin controls and refresh
the recommendation trace panel to inspect parsed intents, ranked offer IDs, and trace steps.

Gate 4E adds a staging UI evaluation panel. Paste the admin token and run the fixture quality checks
to see pass/fail counts for the deterministic recommendation suite without using a terminal.

Gate 4F adds deterministic decision explanations to each recommended offer. The API and staging UI
now show matched intent signals, ranking signals, and guardrails that confirm the recommendation used
stored mock data only.

Gate 4G adds a staging recommendation feedback loop. Each explained recommendation can be marked
Helpful or Not helpful, and admins can inspect aggregate feedback without storing user identity.

Gate 4H upgrades the staging feedback dashboard with Helpful rate, trace feedback coverage, recent
feedback timing, and one quality-loop refresh control for evaluation, traces, feedback, and staging
summary.

Gate 4L adds staging retention controls for recommendation traces and feedback. Admins can preview
old quality events, then prune them only after entering the confirmation phrase.

Gate 4M adds a staging quality cockpit that summarizes fixture status, feedback coverage, trace
volume, and retention readiness in one admin view. It uses the existing mock-only quality endpoints
and does not add Render services or production AI behavior.

Gate 4N adds a staging quality report export. Admins can download a JSON snapshot of evaluation,
feedback, traces, staging counts, and dry-run retention readiness before pruning or changing ranking
logic.

Gate 4O versions the deterministic recommendation strategy, rule set, intent parser, ranker, and
fixture set across API responses, quality reports, staging UI, and staging smoke checks. This keeps
future ranking or AI changes auditable.

Gate 4P stores those recommendation versions on each persisted trace row with an Alembic migration.
Trace audits can now read the exact rule, parser, ranker, and fixture versions saved with the
recommendation event.

Gate 4Q adds a staging trace drilldown in the admin UI. Reviewers can select a recent
recommendation trace and inspect its saved versions, parsed intent, result count, recommended offer
IDs, evaluation steps, and any recently loaded feedback attached to the trace.

Gate 4R adds a trace comparison view. Staging reviewers can compare two recent recommendation
traces across versions, parsed intent fields, result counts, ranked offer IDs, and evaluation steps
before changing ranking logic.

Gate 4S adds an admin closeout checklist to the quality cockpit. It summarizes fixture readiness,
trace audit coverage, feedback coverage, retention preview, export snapshot status, and active
version metadata before final Gate 4 closeout.

Gate 4T closes the recommendation staging phase. The closeout evidence, exit criteria, and remaining
deferrals are recorded in `docs/GATE_4_CLOSEOUT.md`.

Gate 5A starts the constrained LLM intent-parser phase with a contract only. The backend now has
versioned input/output schemas, allowed sort values, guardrails, and fallback policy for a future
LLM parser. No model is called, no endpoint behavior changes, and the deterministic
`intent-parser-v0` remains the active parser.

Gate 5B adds OpenAI-related configuration and a mockable LLM intent-parser service. The default
configuration keeps the service disabled. Tests can inject a mock client to validate schema handling,
confidence fallback, and missing-key fallback without making a network request or calling a model.

Gate 5C wires the parser service into the recommendation flow behind the feature flag. With the
default disabled config, recommendations still use deterministic `intent-parser-v0`; the trace now
records the parser gate fallback before the rule parser step. Tests cover the mock-enabled path
without a live model call.

Gate 5D adds a constrained live OpenAI parser client behind the same feature flag. The route creates
the live client only when `FEATURE_LLM_INTENT_PARSER=true`, `LLM_INTENT_PARSER_MODE=openai`, and
`OPENAI_API_KEY` are all configured. The client requests schema-constrained JSON, validates the
response with the Gate 5A contract, and falls back to `intent-parser-v0` on missing config, request
failure, invalid JSON, schema failure, or low confidence. Staging smoke should remain disabled unless
you are explicitly testing live parser behavior.

Gate 5E closes the constrained parser enablement phase. It adds an admin-only parser status endpoint
and web proxy so staging smoke can verify whether the live parser is disabled safely or explicitly
ready. The status response exposes booleans, parser versions, guardrails, and enablement steps only;
it does not expose `OPENAI_API_KEY`, `ADMIN_API_TOKEN`, prompts, model responses, scraping output, or
affiliate payloads.

Gate 6A adds a mock-only AI router before intent parsing. Defaults are
`FEATURE_AI_ROUTER=false` and `AI_ROUTER_MODE=disabled`. The router never calls a live model and only
exposes `intent-parser-v0`. When enabled in mock mode it still forces the deterministic parser path.
Check status with `GET /admin/router-status`.

Gate 6B upgrades the router with OpenAI/Anthropic/Mock providers, Redis intent caching, cost logging,
and `/admin/router/metrics` plus `/admin/router/config`. Live mode stays off unless explicitly
enabled with provider keys in the environment.

Gate 7 adds a LinUCB contextual bandit (`FEATURE_BANDIT_ROUTER=false` by default). Start in
`BANDIT_ROUTER_MODE=logging` to collect `bandit_logs` without changing routing. Admin endpoints live
under `/admin/bandit/*`; public status is `GET /bandit/status` (web proxy `/api/bandit/status`).

Gate 8 adds anonymous personalization (`FEATURE_PERSONALIZATION=false` by default). Clients send an
opaque `X-Anonymous-User-Id` (no email/phone). Profiles support opt-out; recommendations and bandit
features fall back to the non-personalized path when disabled or opted out.

Gate 9 adds DeepSeek/Qwen/ERNIE providers plus neural/RLHF/Bayesian tooling. All advanced flags
default off (`FEATURE_CHINESE_LLM_PROVIDERS`, `FEATURE_NEURAL_BANDIT`, `FEATURE_RLHF_ROUTER`, etc.).

## Docker Compose

Run the full local stack:

```bash
docker compose up --build
```

If host port `5432` is already in use, stop the conflicting local PostgreSQL service or temporarily
override the published Postgres port.

## Render Staging Blueprint

Staging is provisioned from `render.yaml` as a Render Blueprint. Do not create the frontend, API,
PostgreSQL, or Redis / Key Value services manually.

Before applying the Blueprint in the SaveIQ Render workspace:

1. Enable billing in Render.
2. Configure a Render registry credential named `ghcr-saveiq`.
3. Build and push the prebuilt images:

   ```bash
   docker build -t ghcr.io/<owner>/saveiq-engine:staging apps/api
   docker build -t ghcr.io/<owner>/saveiq-web:staging apps/web
   docker push ghcr.io/<owner>/saveiq-engine:staging
   docker push ghcr.io/<owner>/saveiq-web:staging
   ```

4. Resolve the pushed image digests and replace these placeholders in `render.yaml`:

   - `<CONTAINER_REGISTRY>`
   - `<BACKEND_DIGEST>`
   - `<FRONTEND_DIGEST>`
   - `<STAGING_WEB_HOST>`
   - `<STAGING_API_HOST>`

5. Validate the concrete Blueprint:

   ```bash
   PYTHON=.venv/bin/python make staging-provision-validate
   ```

   The expected output is:

   ```text
   staging_provisioning_validation=ok
   ```

6. Apply the Blueprint in Render, wait for all resources to become healthy, then update
   `docs/STAGING_RESOURCE_REGISTER.md` with resource identifiers, hostnames, image digests, and
   health status. Never place secrets in the register.

The staging Blueprint intentionally uses free web, Postgres, and Key Value instances and defers the
background worker and scheduler until they are needed. Render free Postgres expires after 30 days,
and free Key Value data is in-memory only.

Confirm the staging frontend is not indexable:

```bash
curl -sI https://<web-host>/ | grep -i x-robots-tag
```

The header must include `noindex, nofollow`.

Seed staging with deterministic mock affiliate data and verify both API search and the web search
proxy:

```bash
ADMIN_API_TOKEN=<render-admin-token> PYTHON=.venv/bin/python make staging-seed-mock
```

Run the full staging smoke test after every deploy. It checks API/web health, mock sync, staging
summary, public search, mock recommendations, persisted recommendation traces, click tracking,
recommendation evaluation, parser enablement status, click analytics, and web proxies:

```bash
ADMIN_API_TOKEN=<render-admin-token> PYTHON=.venv/bin/python make staging-smoke
```

The token must come from Render's `ADMIN_API_TOKEN` environment variable. Do not commit it or paste
it into docs.

Gate 3 staging closeout evidence is recorded in `docs/GATE_3_CLOSEOUT.md`.
Gate 4 recommendation closeout evidence is recorded in `docs/GATE_4_CLOSEOUT.md`.
Gate 5 parser enablement closeout evidence is recorded in `docs/GATE_5_CLOSEOUT.md`.

For template-only validation before placeholders are replaced:

```bash
PYTHON=.venv/bin/python make staging-provision-validate-template
```

## Render Production Blueprint (Gate 10A)

Production uses a **separate** Blueprint file: `render-production.yaml` (`saveiq-production`).
Do not share secrets with staging. Auto-deploy is **off**; pin digests, Sync in Render, then smoke.

```bash
PYTHON=.venv/bin/python make production-provision-validate
PYTHON=.venv/bin/python make deploy-production
ADMIN_API_TOKEN=<production-admin-token> PYTHON=.venv/bin/python make production-smoke
```

Operator procedures (deploy, rollback, scaling, troubleshooting): [`docs/RUNBOOK.md`](docs/RUNBOOK.md).  
Gate 10A closeout: [`docs/GATE_10A_CLOSEOUT.md`](docs/GATE_10A_CLOSEOUT.md).

## Security scanning

CI runs `pip-audit`, `npm audit --audit-level=high`, and Trivy (filesystem + published images).
Locally (requires API venv / npm install):

```bash
PYTHON=.venv/bin/python make security-scan
```

## Quality Checks

From the repository root:

```bash
npm run format
npm run lint
npm run typecheck
npm run test
npm run build

cd apps/api
ruff check .
ruff format --check .
mypy app
pytest
```

## Scope Guardrails

This foundation intentionally does not include web scraping, real affiliate network integrations, or
a complete AI agent. The current affiliate connector is a deterministic mock provider only.
