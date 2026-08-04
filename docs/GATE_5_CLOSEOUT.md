# Gate 5 Closeout

Gate 5 establishes a constrained LLM intent-parser boundary without making the full recommendation
system AI-driven. The default staging path remains deterministic and uses `intent-parser-v0`.

## Scope Completed

- Gate 5A defines the versioned parser input/output contract, guardrails, allowed sorts, and
  fallback policy.
- Gate 5B adds disabled-by-default OpenAI settings and a mockable parser service.
- Gate 5C wires the parser service into recommendation traces behind the feature flag.
- Gate 5D adds the controlled OpenAI HTTP parser client behind explicit feature, mode, and key
  requirements.
- Gate 5E adds parser enablement status checks for API, web proxy, smoke testing, and closeout.

## Staging Default

Staging should stay in the safe default state unless a live parser test is deliberate:

```text
FEATURE_LLM_INTENT_PARSER=false
LLM_INTENT_PARSER_MODE=disabled
OPENAI_API_KEY unset
active_parser_version=intent-parser-v0
fallback_parser_version=intent-parser-v0
```

The live parser is considered ready only when all of these are true:

```text
FEATURE_LLM_INTENT_PARSER=true
LLM_INTENT_PARSER_MODE=openai
OPENAI_API_KEY configured as a secret
```

## Verification

Run local checks before deploying:

```bash
npm run format
.venv/bin/ruff format apps/api/app apps/api/tests
.venv/bin/ruff check apps/api/app apps/api/tests
.venv/bin/mypy apps/api/app
npm run lint
npm run typecheck
npm run test
.venv/bin/pytest apps/api/tests
npm run build
PYTHON=.venv/bin/python make recommendation-eval
PYTHON=.venv/bin/python make staging-provision-validate
```

Run staging smoke after Render sync and deploy:

```bash
ADMIN_API_TOKEN=<render-admin-token> PYTHON=.venv/bin/python make staging-smoke
```

Gate 5E staging smoke must include:

```text
llm_parser_status=active=<intent-parser-v0-or-llm-intent-parser-v0> live_ready=<bool> configured=<bool>
web_llm_parser_status_proxy=active=<same-parser-version>
```

## Security Requirements

- Do not expose `OPENAI_API_KEY` or `ADMIN_API_TOKEN` in API responses, docs, logs, tests, or smoke
  output.
- Do not store raw prompts or raw model responses in recommendation traces.
- Do not browse, scrape, call affiliate networks, or invent products, prices, coupons, or cashback.
- Keep deterministic fallback available for missing config, request errors, invalid JSON, schema
  failures, and confidence below `0.60`.

## Rollback

To return staging to deterministic parsing:

```text
FEATURE_LLM_INTENT_PARSER=false
LLM_INTENT_PARSER_MODE=disabled
Remove OPENAI_API_KEY from staging if it is not needed
Manual deploy dealhunter-staging-api
Run staging smoke
```

## Deferred

- Full AI shopping agent orchestration.
- User-specific personalization.
- Real affiliate integrations.
- Web scraping or browser automation.
- Production model evaluation and cost monitoring.
