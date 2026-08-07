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
- Admin-only staging data summary and mock seed controls
- End-to-end staging smoke test for health, seed, search, clicks, analytics, and web proxies
- Keep search grounded in stored normalized data only
- Gate 3 staging closeout completed with live smoke validation

## Phase 3: Approved Affiliate Integrations

- Select first approved partner API or feed.
- Add connector credentials through secret management.
- Normalize provider offers.
- Add provider-specific freshness and attribution policy.

## Phase 4: AI Recommendations

- Gate 4A deterministic recommendation skeleton
- Rule-based intent parser for mock staging queries
- Retrieval through stored normalized offer search
- Inline evaluation trace for parse, retrieval, and ranking steps
- Recommendation explanations grounded in existing match and ranking reasons
- Gate 4B offline evaluation fixtures for recommendation regressions
- Deterministic recommendation evaluator for local and CI checks
- Gate 4C persisted recommendation traces for staging audit
- Admin trace inspection endpoint and staging smoke coverage
- Gate 4D staging UI trace viewer for parsed intents and trace steps
- Gate 4E staging evaluation panel for deterministic fixture pass/fail checks
- Gate 4F deterministic decision explanations for each recommended offer
- Gate 4G staging Helpful/Not helpful feedback loop for recommendations
- Gate 4H staging feedback dashboard with Helpful rate and trace feedback coverage
- Gate 4L staging retention controls for recommendation traces and feedback
- Gate 4M staging quality cockpit for evaluation, coverage, trace volume, and retention readiness
- Gate 4N staging quality report export for review snapshots before pruning or ranking changes
- Gate 4O versioned recommendation rules, parser, ranker, fixture set, and quality export metadata
- Gate 4P persisted recommendation trace version columns and row-level trace audit display
- Gate 4Q staging recommendation trace drilldown with parsed intent, versions, steps, and feedback
- Gate 4R staging recommendation trace comparison before ranking or parser changes
- Gate 4S admin closeout checklist for fixture, trace, feedback, retention, export, and version readiness
- Gate 4T final recommendation staging closeout

## Phase 5: Constrained LLM Intent Parser

- Gate 5A versioned LLM intent-parser contract, schema guardrails, and fallback policy
- Gate 5B OpenAI configuration and mockable parser service
- Gate 5C feature-flagged parser path wired into recommendations behind deterministic fallback
- Gate 5D controlled live OpenAI parser client behind feature flag, schema validation, and fallback
- Gate 5E staging parser enablement status, smoke coverage, and closeout

## Phase 6: AI Router And Assistant Shell

- Gate 6A mock-only AI router before intent parsing, disabled by default, deterministic fallback
- Gate 6B production AI router with OpenAI/Anthropic/Mock providers, Redis cache, cost logs, metrics
- Later: assistant shell remains deferred until controlled enablement gates

## Phase 7: Contextual Bandit Router Optimization

- Gate 7 LinUCB bandit with logging-first mode, `bandit_logs` persistence, offline train, admin/public status

## Phase 8: Personalization And User Context

- Gate 8 anonymous user profiles, opt-out, embedding features for bandit, category-boost recommendations

## Phase 9: Super Intelligence Integration

- Gate 9 Chinese LLM providers (DeepSeek/Qwen/ERNIE), neural/RLHF policies, Bayesian tuning, benchmarks
