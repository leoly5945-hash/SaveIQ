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

## 2026-07-25: Gate 4G Feedback Stores Quality Signals Without Identity

Status: Accepted

Recommendation feedback stores trace ID, offer ID, rating, source, provider source, market, and
timestamp. It does not store user identity or session fingerprints. This gives staging a lightweight
quality loop while keeping privacy and production-readiness risks low.

## 2026-07-25: Gate 4H Feedback Dashboard Is Staging-Only

Status: Accepted

The feedback dashboard aggregates Helpful rate and trace feedback coverage from stored staging
events. It helps reviewers inspect recommendation quality before any LLM layer exists. It does not
train a model, store identity, or send feedback to external services.

## 2026-07-25: Gate 4L Retention Requires Dry-Run And Confirm

Status: Accepted

Recommendation quality retention is limited to staging trace and feedback events. It defaults to
dry-run previews and requires the explicit `DELETE_STAGING_QUALITY_EVENTS` confirmation phrase before
deleting old events. This keeps staging data bounded while avoiding accidental deletion of normalized
offers, click analytics, or sync history.

## 2026-07-26: Gate 4M Quality Cockpit Stays Web-Only

Status: Accepted

The recommendation quality cockpit is a staging web aggregation of existing evaluation, feedback,
trace, staging summary, and retention-preview data. It does not add a backend aggregate endpoint yet
because the existing admin proxies already provide the needed signals. This keeps the gate small,
cost-neutral, and mock-only while making quality review easier for non-terminal staging checks.

## 2026-07-26: Gate 4N Quality Export Is Snapshot-Only

Status: Accepted

The recommendation quality export is a staging-only JSON snapshot that combines existing evaluation,
feedback, trace, staging summary, and dry-run retention data. It exists to preserve review evidence
before pruning or ranking-rule changes. The export avoids admin tokens, user identity, live AI
outputs, scraping data, and real affiliate-network data.

## 2026-07-27: Gate 4O Versions Rules Before AI Changes

Status: Accepted

Recommendation strategy, rule set, intent parser, ranker, and fixture set versions are centralized
and surfaced through recommendation responses, evaluation summaries, trace admin responses, quality
exports, staging UI, and smoke checks. This gives staging a stable audit marker before future ranking
or AI changes. The current database trace row still stores only the strategy; per-trace rule-version
columns are deferred until historical production trace semantics are needed.

## 2026-07-27: Gate 4P Persists Version Metadata Per Trace

Status: Accepted

Recommendation trace rows now store rule, parser, ranker, and fixture versions alongside the
strategy. Existing staging rows are backfilled to the Gate 4O metadata by migration. This makes trace
audits historical instead of only comparing against current metadata, while still avoiding user
identity, live AI payloads, scraping output, or real affiliate-network data.

## 2026-07-27: Gate 4Q Keeps Trace Drilldown UI-Only

Status: Accepted

The recommendation trace drilldown is built in the staging web UI from existing trace and feedback
summary proxy responses. It intentionally avoids a new backend endpoint because the required row
versions, parsed intent, ranked offer IDs, evaluation steps, and recent feedback are already present
in the admin payloads. This keeps the gate small and avoids expanding staging infrastructure.

## 2026-07-27: Gate 4R Compares Traces Without Expanding the API

Status: Accepted

Trace comparison is implemented client-side from the existing recent trace payload. Comparing
versions, parsed intent, result count, ranked offer IDs, and evaluation step outputs is enough for
staging reviewers to spot ranking changes before the system introduces real AI parsing. A dedicated
compare endpoint is deferred until traces become large enough to need server-side diffing.

## 2026-07-28: Gate 4S Uses a UI Checklist for Phase Readiness

Status: Accepted

Gate 4 closeout readiness is represented as a staging UI checklist instead of a new backend status
endpoint. The cockpit already has all required source data from evaluation, traces, feedback,
retention preview, quality export, and version metadata. Keeping the readiness calculation in the UI
avoids expanding the API before the recommendation quality rules stabilize.

## 2026-07-29: Gate 4T Closes The Deterministic Recommendation Phase

Status: Accepted

Gate 4 is closed with deterministic recommendations, fixture evaluation, persisted traces, version
metadata, explanations, feedback, retention preview, trace comparison, quality export, and staging
smoke coverage. The next phase should prototype LLM intent parsing behind these existing guardrails
rather than introducing a full autonomous agent or real affiliate integrations.

## 2026-07-29: Gate 5A Defines Parser Contract Before Model Calls

Status: Accepted

The LLM intent-parser phase starts with versioned input/output schemas, allowed sort values,
guardrails, and fallback policy before adding OpenAI configuration or model execution. The active
recommendation parser remains deterministic `intent-parser-v0`, and low-confidence, invalid,
misconfigured, or failed LLM parsing must fall back to it. This keeps Gate 5 small, auditable, and
mock-only while preserving the existing evaluation and trace foundation.

## 2026-07-29: Gate 5B Keeps OpenAI Behind An Injected Client

Status: Accepted

OpenAI configuration is added before any live model execution. The LLM parser service accepts an
injected client and falls back unless the feature flag, parser mode, key requirements, schema
validation, and confidence threshold all pass. This lets local tests and future staging checks
exercise the parser boundary with a mock client while avoiding accidental network calls, spend, or
unreviewed model output.

## 2026-07-30: Gate 5C Wires The Parser Behind Fallback

Status: Accepted

The recommendation route now passes runtime settings into the LLM parser service, but the default
configuration still falls back to deterministic `intent-parser-v0`. Route-driven traces include a
parser-gate step so staging can prove why deterministic parsing was used. The mock-enabled parser
path is covered in tests through an injected client, keeping live model calls and OpenAI spend out of
Gate 5C.

## 2026-07-30: Gate 5D Adds Live Parser Only Behind Explicit Controls

Status: Accepted

The first live OpenAI parser client is implemented inside the existing parser service boundary. It
is only attached when the feature flag is enabled, parser mode is `openai`, and `OPENAI_API_KEY` is
configured. The client sends constrained parser input, requests schema-shaped JSON, validates the
response locally, and falls back to `intent-parser-v0` on request errors, invalid JSON, schema
failure, or low confidence. Tests use a fake HTTP transport so CI and staging smoke do not depend on
OpenAI network access or spend.

## 2026-08-04: Gate 5E Closes Parser Enablement With Status Checks

Status: Accepted

The constrained LLM parser phase closes with an admin-only parser status endpoint instead of turning
the model on by default. Staging can now prove that the live parser is either safely disabled or
explicitly ready through feature flag, mode, and secret presence checks. The endpoint returns
versions, guardrails, readiness booleans, and required enablement steps, but never returns API keys,
admin tokens, prompts, raw model responses, scraping output, or affiliate payloads. Staging smoke
checks the API endpoint and web proxy before validating recommendation behavior.
