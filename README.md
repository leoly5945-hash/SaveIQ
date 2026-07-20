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

The token must come from Render's `ADMIN_API_TOKEN` environment variable. Do not commit it or paste
it into docs.

For template-only validation before placeholders are replaced:

```bash
PYTHON=.venv/bin/python make staging-provision-validate-template
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
