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
