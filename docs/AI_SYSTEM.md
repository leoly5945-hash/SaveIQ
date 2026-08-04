# AI System

The full AI system is not implemented in this foundation. The architecture reserves space for a
future assistant that can interpret user intent, retrieve candidate offers, rank results, and explain
recommendations.

Gate 4A adds a deterministic recommendation skeleton only. It exposes `POST /recommendations`,
parses shopping intent with simple rules, reuses stored normalized search data, and returns an
`evaluation_trace` describing parse, retrieval, and ranking steps. It does not call an LLM.

## Intended Responsibilities

- Parse shopping intent and constraints.
- Retrieve relevant products and offers.
- Use vector search for semantic matching when appropriate.
- Rank recommendations using transparent signals.
- Explain tradeoffs without inventing facts.

## Guardrails

- Ground recommendations in stored offer data.
- Clearly separate model-generated explanation from provider facts.
- Do not claim live price or availability unless recently verified.
- Avoid scraping as a data acquisition strategy.
- Log recommendation inputs and outputs for evaluation.
- Keep Gate 4A recommendation output labeled as `rule_based_mock_v0`.
- Keep recommendation rules, parser, ranker, and fixture versions explicit before changing ranking
  behavior or adding live AI.
- Treat persisted Gate 4C traces as staging audit scaffolding, not production observability.

## Future Modules

- Intent classification
- Retrieval orchestration
- Ranking policies
- Recommendation trace retention policy
- Evaluation harness

## Gate 4A Skeleton

The current recommendation skeleton supports:

- intent text between 3 and 240 characters
- limit between 1 and 10 recommendations
- coupon, cashback, freshness, popularity, and price-sort hints
- retrieval through the existing normalized offer search service
- deterministic trace steps with no secrets, user identifiers, or external calls

Known limits:

- numeric constraints such as "under $120" are not enforced yet
- no personalization or user profile is used
- no semantic/vector retrieval is used
- traces are persisted for staging audit, but no user identity is stored

## Gate 4B Evaluation Fixtures

Gate 4B adds offline fixtures at
`apps/api/tests/fixtures/recommendation_eval_cases.json` and a runner at
`scripts/evaluate_recommendations.py`.

The evaluator:

- seeds a temporary in-memory database with the deterministic mock provider
- runs fixed shopping intents through the recommendation service
- validates parsed filters, strategy, minimum result count, first source record, first merchant, and
  trace notes
- keeps all checks local, deterministic, and mock-only

Run it with:

```bash
PYTHON=.venv/bin/python make recommendation-eval
```

Passing output starts with:

```text
recommendation_eval=ok
```

## Gate 4C Persisted Traces

Gate 4C stores each recommendation request in `recommendation_trace_events`. The stored event
contains:

- deterministic strategy name
- raw intent and parsed intent fields
- result count and recommended offer IDs
- trace steps already returned by `POST /recommendations`

The trace event intentionally does not store user identity, IP address, admin token, model prompts,
or model responses.

## Gate 4D Trace Viewer

Gate 4D adds a staging-only admin UI panel for recent recommendation traces. It displays total
traces, raw intent, parsed intent fields, recommended offer IDs, result count, and each deterministic
trace step. The panel reads through the existing web proxy and requires the staging admin token.

## Gate 4E Evaluation Panel

Gate 4E exposes the deterministic recommendation fixture suite through an admin-only staging panel.
The API runs fixtures against an isolated in-memory database seeded from the mock provider, so the
evaluation does not mutate staging data or call external systems. The panel shows status, pass/fail
counts, fixture intents, first expected source records, merchants, and required trace steps.

## Gate 4F Decision Explanations

Gate 4F adds a deterministic `decision_explanation` object to each recommended offer. The explanation
contains:

- `summary`: short reader-facing reason for the selected offer
- `matched_intent`: query, coupon, cashback, and freshness signals that matched the request
- `ranking_signals`: reused transparent search ranking reasons such as price and mock clicks
- `guardrails`: staging constraints, including no model call, no web scraping, and no real affiliate
  network request

These explanations are generated from stored normalized mock offer fields and the parsed intent. They
are not AI-generated text and should remain predictable until a future LLM layer has evaluation gates.

## Gate 4G Feedback Loop

Gate 4G records staging feedback on individual recommended offers. A recommendation can be marked
`helpful` or `not_helpful` only when the offer belongs to the saved trace event. Feedback records
store trace ID, offer ID, rating, source, provider source, market, and timestamp.

This is a quality signal for future evaluation work. It deliberately avoids account identity, browser
fingerprinting, real affiliate calls, and model training behavior.

## Gate 4H Feedback Dashboard

Gate 4H adds a staging-only quality dashboard for recommendation feedback. It shows total feedback,
Helpful rate, trace feedback coverage, recent feedback records, and a single refresh control for
evaluation, traces, feedback, and staging summary. It remains a deterministic review surface and does
not train a model or call a live AI service.

## Gate 4L Retention Controls

Gate 4L adds staging-only retention controls for recommendation trace and feedback events. Admins can
preview how many old events would be removed, then prune only after sending the confirmation phrase
`DELETE_STAGING_QUALITY_EVENTS`. The retention flow protects staging from unbounded quality-event
growth without touching normalized offers, clicks, sync jobs, real user identity, or external
services.

## Gate 4M Quality Cockpit

Gate 4M adds a staging-only recommendation quality cockpit to the web admin surface. It summarizes
fixture evaluation status, feedback coverage, trace volume, and retention preview state in one place
so reviewers can decide whether the mock recommendation loop is ready for the next gate. It reuses
existing deterministic endpoints and does not introduce a live AI model, external scoring service, or
new production data collection.

## Gate 4N Quality Report Export

Gate 4N adds a staging-only JSON export for recommendation quality review. The export captures the
current fixture evaluation, feedback summary, recent traces, staging counts, and dry-run retention
preview. It is designed as an audit snapshot before pruning old staging quality events or changing
ranking rules. It does not include admin tokens, user identity, scraping output, or model-generated
content.

## Gate 4O Versioned Recommendation Rules

Gate 4O centralizes recommendation version metadata for the deterministic mock recommender:

- strategy: `rule_based_mock_v0`
- rule version: `ruleset-2026-07-27-gate-4o`
- intent parser: `intent-parser-v0`
- ranker: `ranker-v0`
- fixture set: `fixtures-v0`

The API response, fixture evaluation summary, trace admin endpoint, quality export, staging UI, and
smoke test all expose or validate these values.

## Gate 4P Persisted Trace Versions

Gate 4P adds persisted rule, parser, ranker, and fixture version columns to
`recommendation_trace_events`. Existing staging trace rows receive the Gate 4O defaults during
migration, and new traces store the versions at creation time. The trace admin endpoint and staging
UI now show row-level version metadata, so future ranking or AI changes can be audited trace by
trace.

## Gate 4Q Trace Drilldown

Gate 4Q adds a staging-only trace detail view to the admin UI. It uses the existing trace and
feedback summary proxy endpoints, so no new API surface or Render service is required. Reviewers can
select a recent trace and inspect the saved recommendation versions, parsed intent fields, result
count, recommended offer IDs, deterministic evaluation steps, and attached feedback that has already
been loaded in the quality cockpit.

## Gate 4R Trace Comparison

Gate 4R adds a staging-only comparison panel for recent recommendation traces. The UI compares the
selected trace against another trace across rule, parser, ranker, fixture versions, parsed intent
fields, result count, recommended offer IDs, and deterministic evaluation step outputs. This is a
review aid before ranking or AI parser changes and does not add new persistence, external model
calls, scraping, or affiliate integrations.

## Gate 4S Admin Closeout Checklist

Gate 4S adds a staging-only closeout checklist to the recommendation quality cockpit. It summarizes
fixture status, trace audit volume, feedback coverage, retention preview readiness, quality export
status, and active version metadata. The checklist is a review surface only; it does not alter
recommendation behavior, persistence, external integrations, or AI execution.

## Gate 4T Recommendation Phase Closeout

Gate 4T closes the deterministic recommendation staging phase. The system now has enough mock-only
quality scaffolding to evaluate future AI changes: fixtures, persisted traces, row-level versions,
decision explanations, feedback, retention preview, trace comparison, and quality export. The next
AI step should be a constrained LLM intent-parser prototype behind the same evaluation and trace
surfaces, not a full autonomous agent.

## Gate 5A LLM Intent Parser Contract

Gate 5A defines the contract for a future LLM-powered intent parser without calling a model or
changing recommendation endpoint behavior. The contract lives in
`apps/api/app/services/llm_intent_contract.py` and includes:

- contract version: `llm-intent-contract-2026-07-29-gate-5a`
- prompt version: `llm-intent-prompt-v0`
- output schema name: `dealhunter.recommendation_intent.v1`
- allowed sorts: `price_asc`, `price_desc`, and `clicks_desc`
- fallback parser: `intent-parser-v0`

The parser input is limited to the raw shopping intent, market, locale, and allowed sort values. The
parser output is limited to normalized search query, coupon/cashback flags, freshness, sort,
confidence, reasoning summary, and optional fallback reason.

The fallback policy keeps the deterministic parser active when the feature flag is disabled, API key
configuration is missing, model calls fail, model output fails schema validation, or confidence is
below `0.60`.

Guardrails require the future parser to parse shopping intent only, return only declared schema
fields, avoid inventing merchants, products, prices, coupons, or cashback, and avoid browsing or
calling affiliate networks. Gate 5A is intentionally contract-only; the OpenAI configuration,
mockable parser service, feature flag, and trace integration are deferred to later Gate 5 steps.

## Gate 5B Mockable LLM Parser Service

Gate 5B adds the configuration and service boundary for the future LLM intent parser. The active
recommendation endpoint still uses deterministic `intent-parser-v0`; this gate does not wire the LLM
parser into user-facing recommendations.

New configuration:

- `FEATURE_LLM_INTENT_PARSER`, default `false`
- `LLM_INTENT_PARSER_MODE`, default `disabled`, allowed `disabled`, `mock`, or `openai`
- `OPENAI_API_KEY`, optional and never committed
- `OPENAI_INTENT_MODEL`, default `gpt-4.1-mini`
- `OPENAI_INTENT_TIMEOUT_SECONDS`, default `10`

The service in `apps/api/app/services/llm_intent_parser.py` accepts an injected parser client. Tests
use a mock client so Gate 5B can validate schema parsing, invalid-output fallback, low-confidence
fallback, missing-key fallback, and timeout/model propagation without making network requests.

Fallback remains mandatory when the feature flag is off, parser mode is disabled, OpenAI mode is
selected without an API key, no client is available, output fails validation, or confidence is below
`0.60`.

## Gate 5C Feature-Flagged Parser Path

Gate 5C wires the mockable parser service into `POST /recommendations` while keeping the default
staging behavior deterministic. The route creates `LlmIntentParserService` from runtime settings and
passes it to the recommendation service. With `FEATURE_LLM_INTENT_PARSER=false`, the service records
a fallback result and recommendations continue through `intent-parser-v0`.

The persisted recommendation trace now includes a `llm_intent_parser` step before `parse_intent` for
route-driven recommendations. In disabled staging, that step records `fallback to intent-parser-v0`.
When tests inject a mock parser client and enable `LLM_INTENT_PARSER_MODE=mock`, the recommendation
service can accept the parsed schema output and store `llm-intent-parser-v0` as the trace parser
version.

No OpenAI SDK call, external network request, scraping, autonomous agent behavior, or real affiliate
integration is introduced in Gate 5C.

## Gate 5D Controlled Live Parser Client

Gate 5D introduces a live OpenAI parser client behind the existing parser service boundary. The
recommendation route still creates the parser from runtime settings, but the OpenAI HTTP client is
attached only when all live-parser controls are present:

- `FEATURE_LLM_INTENT_PARSER=true`
- `LLM_INTENT_PARSER_MODE=openai`
- `OPENAI_API_KEY` is configured

The client sends only the constrained Gate 5A parser input, guardrails, prompt version, and allowed
sort values. It requests JSON shaped by the Gate 5A output schema and then validates the model output
with `LlmParsedIntent` before any recommendation filters are used.

Fallback remains mandatory when config is incomplete, the request fails, the model response is not
valid JSON, schema validation fails, or confidence is below `0.60`. When fallback happens,
recommendations still use deterministic `intent-parser-v0` and trace the fallback reason. When a
live parser output is accepted, only intent parsing used the model; retrieval, ranking, offer facts,
prices, coupons, cashback, and click data still come from stored normalized mock records.

Gate 5D does not implement a full AI agent, web scraping, browser access, real affiliate
integrations, autonomous actions, or model training.

## Gate 5E Parser Enablement Closeout

Gate 5E closes the constrained LLM intent-parser enablement phase without enabling the live parser by
default. The recommendation path remains deterministic on staging unless all explicit live-parser
controls are set.

The admin-only status endpoint reports the current parser state:

- feature flag enabled/disabled
- parser mode
- whether an OpenAI key is configured, as a boolean only
- active and fallback parser versions
- live-parser readiness
- staging-safe default status
- guardrails and required enablement steps

The endpoint and web proxy intentionally do not return `OPENAI_API_KEY`, `ADMIN_API_TOKEN`, raw
prompts, raw model responses, scraping output, or affiliate payloads. Staging smoke now checks this
status before validating recommendation behavior so accidental parser enablement is visible before
future gates change ranking or personalization.
