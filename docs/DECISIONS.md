# Decisions

## 2026-07-10: Use Modular Monolith

Status: Accepted

DealHunter starts as a modular monolith with clear internal package boundaries. This reduces
operational overhead while the product surface and data model are still forming.

## 2026-07-10: Use PostgreSQL With pgvector

Status: Accepted

PostgreSQL is the primary store and pgvector is enabled for future semantic retrieval. Vector fields
remain optional until the AI retrieval system is implemented.

## 2026-07-10: No Web Scraping

Status: Accepted

DealHunter will use approved APIs, feeds, or partner data access. Web scraping is outside the
intended architecture.

## 2026-07-18: Rename To DealHunter AI

Status: Accepted

The public product brand is DealHunter AI. Public branding is now exposed through configuration
where practical.

## 2026-07-18: Affiliate Connectors Are Provider Plugins

Status: Accepted

Future affiliate integrations should implement the provider adapter protocol and register with the
provider registry. Provider mapping must remain isolated from core product and offer logic.

## 2026-07-18: Deterministic Matching Only

Status: Accepted

Product resolution uses exact identifiers and brand plus MPN matching. LLM-based matching is deferred
until evaluation and review workflows exist.

## 2026-07-24: Gate 4A Uses Rule-Based Recommendations

Status: Accepted

The first recommendation surface is a deterministic skeleton that reuses normalized stored search
data and returns an inline evaluation trace. It intentionally avoids LLM calls, real affiliate
integrations, web scraping, personalization, and persisted trace storage until evaluation criteria
and production guardrails are defined.

## 2026-07-24: Gate 4B Recommendation Evaluation Is Offline

Status: Accepted

Recommendation evaluation fixtures run against a temporary in-memory database seeded from the mock
provider. This keeps regression checks deterministic, cheap, and safe while the project has no real
affiliate connectors, user personalization, or LLM orchestration.

## 2026-07-25: Gate 4C Persists Recommendation Traces Without User Identity

Status: Accepted

Each recommendation request writes a `recommendation_trace_events` row containing the deterministic
strategy, raw intent, parsed intent, result count, recommended offer IDs, and trace steps. The trace
store is admin-only staging audit scaffolding and intentionally excludes user identity, IP address,
tokens, real affiliate payloads, and model prompts or responses.

## 2026-07-25: Gate 4D Trace Viewer Is Staging Admin Only

Status: Accepted

The first trace viewer lives inside the staging UI admin area and reads from the existing
admin-protected recommendation trace proxy. It is intentionally read-only and does not expose traces
without the staging admin token.

## 2026-07-25: Gate 4E Evaluation Runs Against Isolated Fixtures

Status: Accepted

The staging evaluation panel runs the deterministic recommendation fixtures against an isolated
in-memory database seeded from the mock provider. This gives admins a low-cost pass/fail quality
signal without mutating staging data, calling external affiliate systems, or invoking an LLM.

## 2026-07-25: Gate 4F Explanations Are Deterministic

Status: Accepted

Recommendation explanations are composed from parsed intent fields, search match reasons, ranking
reasons, and fixed guardrails. This keeps staging explainability inspectable without creating a new
LLM dependency, scraping behavior, or live affiliate-network integration.
