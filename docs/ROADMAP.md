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
- Sort controls and basic match explanations
- Offer detail view with source attribution and mock commercial context
- Lightweight mock click tracking for product and affiliate link taps
- Staging-only mock click analytics for top offers, merchants, and recent events
- Search ranking option that sorts stored mock offers by click count
- Rule-based ranking reasons for staging explainability
- Keep search grounded in stored normalized data only

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
