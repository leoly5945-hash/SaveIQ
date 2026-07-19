# Architecture

DealHunter uses a modular monolith architecture. The backend is one FastAPI service with internal
modules for API routes, database access, affiliate providers, ingestion, and domain models.

## Components

- `apps/web`: Next.js frontend.
- `apps/api`: FastAPI backend.
- PostgreSQL with pgvector: relational store and future vector retrieval.
- Redis: future cache, rate-limit, and background coordination backend.
- Alembic: database migrations.
- Docker Compose: local development infrastructure.

## Backend Modules

- `app.api`: HTTP route boundaries.
- `app.core`: settings and application configuration.
- `app.db`: SQLAlchemy base, engine, sessions.
- `app.models`: affiliate domain persistence models.
- `app.services.affiliate`: provider adapters, registry, mock provider, ingestion pipeline.

## Ingestion Flow

Mock provider → raw record storage → validation → normalization → product resolution → merchant
listing resolution → offer upsert → price history append → coupon/cashback update → sync job result.

The pipeline uses nested transactions per record. A malformed record is rejected and audited without
failing the entire sync. Critical failures roll back the job.

## Idempotency

Raw records are deduplicated by provider, source record ID, and content hash. Offers, listings,
affiliate links, coupons, and cashback records are upserted by provider source and source record ID.
Price history appends only new observations.
