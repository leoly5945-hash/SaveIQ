# Roadmap

## Phase 0: Foundation

- Next.js frontend scaffold
- FastAPI backend scaffold
- PostgreSQL, pgvector, Redis local configuration
- Health checks
- Alembic migrations
- CI and quality tooling

## Phase 1: Affiliate Domain Foundation

- Affiliate domain tables
- Provider adapter contract
- Deterministic Canadian mock provider
- Idempotent mock ingestion pipeline
- Protected admin visibility endpoints

## Phase 2: Search Slice

- Product and offer search endpoint
- Basic frontend search UI
- Filters by merchant, brand, category, coupon, cashback, and freshness

## Phase 3: Approved Affiliate Integrations

- Select first approved partner API or feed.
- Add connector credentials through secret management.
- Normalize provider offers.
- Add provider-specific freshness and attribution policy.

## Phase 4: AI Recommendations

- Intent parser
- Retrieval and ranking orchestration
- Recommendation explanations
- Evaluation traces and test fixtures
