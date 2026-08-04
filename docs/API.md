# API

The public API currently exposes health, mock search, offer detail, rule-based mock
recommendations, and mock click tracking endpoints.
Development/admin affiliate endpoints are protected by the `X-Admin-Token` header and are intended
for local or staging visibility.

## Public

`GET /health`

```json
{
  "status": "ok",
  "service": "DealHunter API",
  "version": "0.1.0"
}
```

`GET /search/offers/{offer_id}`

Fetch a single normalized mock offer with commercial context, source attribution, and recent price
history.

```json
{
  "offer_id": 1,
  "product_id": 1,
  "title": "Aurora WaveBuds",
  "merchant": "Maple Tech",
  "affiliate_url": "https://affiliate.example.test/mt-wavebuds",
  "source_attribution": {
    "provider_source": "mock_ca",
    "source_record_id": "mt-wavebuds-offer",
    "source_timestamp": "2026-07-09T10:00:00Z",
    "last_successful_update": "2026-07-21T04:00:00Z",
    "record_status": "active"
  },
  "coupons": [],
  "cashback_offers": [],
  "price_history": []
}
```

`GET /search`

Search normalized mock affiliate offers. The endpoint is public, read-only, and uses only stored
provider-normalized data.

Query parameters:

- `q`: product, offer, merchant, brand, or category text.
- `merchant`: merchant name filter.
- `brand`: exact brand name filter.
- `category`: exact category name filter.
- `has_coupon`: `true` or `false`.
- `has_cashback`: `true` or `false`.
- `freshness`: `fresh`, `stale`, or `unknown`.
- `sort`: `price_asc`, `price_desc`, `clicks_desc`, or `merchant`; default `price_asc`.
- `limit`: 1-50 results, default 20.

```json
{
  "query": "buds",
  "count": 2,
  "results": [
    {
      "offer_id": 1,
      "product_id": 1,
      "title": "Aurora WaveBuds",
      "offer_title": "Aurora WaveBuds Wireless Earbuds",
      "merchant": "Maple Tech",
      "brand": "Aurora",
      "category": "Audio",
      "price_cents": 12999,
      "sale_price_cents": 9999,
      "currency": "CAD",
      "market": "CA",
      "availability": "in_stock",
      "freshness_status": "fresh",
      "provider_source": "mock_ca",
      "product_url": "https://example.test/products/aurora-wavebuds",
      "has_coupon": true,
      "has_cashback": true,
      "click_count": 2,
      "match_reasons": ["product title", "offer title"],
      "ranking_reasons": [
        "lower current price: 99.99 CAD",
        "sale price available",
        "coupon available",
        "fresh mock data"
      ]
    }
  ]
}
```

`POST /clicks`

Record a best-effort click against a stored mock offer target. This endpoint is public so the
staging frontend can track product and mock affiliate link clicks without exposing admin credentials.
It returns the URL that was tracked; the browser still opens the visible link target directly.

```json
{
  "offer_id": 1,
  "target_type": "product",
  "referrer": "https://dealhunter-staging-web.onrender.com/"
}
```

Supported `target_type` values:

- `product`
- `affiliate`

`POST /recommendations`

Return deterministic mock recommendations from stored normalized offers. This is the Gate 4A AI
skeleton: it parses a short shopping intent with rules, reuses the stored search index, and returns
an evaluation trace. It does not call an LLM, scrape the web, or contact affiliate networks.
The staging web app proxies the same request at `POST /api/recommendations`.
Gate 4B regression fixtures validate this response shape and trace behavior offline with
`make recommendation-eval`.
Gate 4C persists each recommendation trace for admin audit and returns `trace_event_id`.
Gate 4F adds `decision_explanation` to each recommended offer so staging can show why a result was
selected without calling an LLM.
Gate 4G adds `POST /recommendations/feedback` for staging Helpful/Not helpful quality signals.
Gate 4O adds explicit recommendation version metadata so staging can prove which rules, parser,
ranker, and fixture set produced a result.
Gate 4Q does not add a new endpoint; the staging trace drilldown reads existing recommendation trace
and feedback summary admin responses through the web proxy.
Gate 4R also uses the same trace payload for UI-side comparison and does not change API contracts.
Gate 4S is also UI-only and adds no API fields or routes.
Gate 4T closes the phase with documentation and does not change API contracts.
Gate 5A defines an internal LLM intent-parser contract only. It adds no endpoint, request field,
response field, model call, scraping behavior, or affiliate integration.
Gate 5B adds configuration and an internal mockable parser service only. It also adds no endpoint,
request field, response field, model call, scraping behavior, or affiliate integration.
Gate 5C keeps the same endpoint and response shape, but route-driven recommendation traces include a
`llm_intent_parser` step before deterministic `parse_intent`. With default staging config, that step
records fallback to `intent-parser-v0`.
Gate 5D adds a controlled live OpenAI parser client behind the same settings. The public request and
response shape are unchanged. If the live parser is enabled and accepted, `intent_parser_version`
becomes `llm-intent-parser-v0` and trace notes show that model output was used only for intent
fields. If config is incomplete or the model path fails, the endpoint falls back to
`intent-parser-v0`.
Gate 5E adds an admin-only parser status endpoint and web proxy for staging enablement checks. It
does not change public recommendation request or response fields.

```json
{
  "intent": "Find fresh wireless earbuds with a coupon",
  "limit": 3
}
```

Abridged example response:

```json
{
  "strategy": "rule_based_mock_v0",
  "rule_version": "ruleset-2026-07-27-gate-4o",
  "intent_parser_version": "intent-parser-v0",
  "ranker_version": "ranker-v0",
  "trace_event_id": 1,
  "count": 1,
  "intent": {
    "raw_intent": "Find fresh wireless earbuds with a coupon",
    "search_query": "wireless earbuds",
    "has_coupon": true,
    "has_cashback": null,
    "freshness": "fresh",
    "sort": "price_asc"
  },
  "recommendations": [
    {
      "offer_id": 1,
      "title": "Aurora WaveBuds Noise Cancelling Earbuds",
      "merchant": "Maple Tech",
      "sale_price_cents": 9999,
      "has_coupon": true,
      "ranking_reasons": [
        "lower current price: 99.99 CAD",
        "sale price available"
      ],
      "decision_explanation": {
        "summary": "Maple Tech matched wireless earbuds; ranked by price_asc; current price 99.99 CAD; coupon available",
        "matched_intent": [
          "matched query text",
          "coupon requested and available",
          "fresh freshness requested"
        ],
        "ranking_signals": [
          "lower current price: 99.99 CAD",
          "sale price available"
        ],
        "guardrails": [
          "uses stored normalized mock offers",
          "no model call",
          "no web scraping",
          "no real affiliate network request"
        ]
      }
    }
  ],
  "evaluation_trace": [
    {
      "step": "llm_intent_parser",
      "input": "disabled",
      "output": "fallback to intent-parser-v0",
      "notes": [
        "LLM parser attempted",
        "mode=disabled",
        "model=gpt-4.1-mini",
        "feature flag disabled"
      ]
    },
    {
      "step": "parse_intent",
      "input": "Find fresh wireless earbuds with a coupon",
      "output": "query='wireless earbuds', has_coupon=True, has_cashback=None, freshness=fresh, sort=price_asc",
      "notes": ["rule-based parser", "intent-parser-v0", "no model call"]
    },
    {
      "step": "retrieve_candidates",
      "input": "stored offers limit=3",
      "output": "1 candidates",
      "notes": ["uses normalized database records", "no web scraping"]
    },
    {
      "step": "rank_candidates",
      "input": "price_asc",
      "output": "1 ranked recommendations",
      "notes": [
        "reuses transparent search ranking reasons",
        "deterministic mock strategy",
        "ranker-v0"
      ]
    }
  ]
}
```

`POST /recommendations/feedback`

Record staging feedback for a recommended offer. The `offer_id` must belong to the supplied
`trace_event_id`. This endpoint stores no user identity.

```json
{
  "trace_event_id": 1,
  "offer_id": 1,
  "rating": "helpful",
  "source": "staging_ui"
}
```

The staging web app proxies the same request at `POST /api/recommendation-feedback`.

## Admin Affiliate

- `POST /admin/affiliate/sync/mock`
- `GET /admin/affiliate/sync/jobs`
- `GET /admin/affiliate/sync/errors`
- `GET /admin/affiliate/products`
- `GET /admin/affiliate/listings`
- `GET /admin/affiliate/offers`
- `GET /admin/affiliate/price-history`
- `GET /admin/affiliate/coupons`
- `GET /admin/affiliate/cashback`
- `GET /admin/affiliate/clicks`
- `GET /admin/affiliate/click-analytics`
- `GET /admin/affiliate/recommendation-traces`
- `GET /admin/affiliate/recommendation-evaluation`
- `GET /admin/affiliate/recommendation-feedback`
- `POST /admin/affiliate/recommendation-quality/retention`
- `GET /admin/affiliate/recommendation-quality/export`
- `GET /admin/affiliate/llm-parser-status`
- `GET /admin/affiliate/staging-summary`

Admin responses expose normalized operational data and do not expose provider secrets or full raw
payloads.

`GET /admin/affiliate/click-analytics` returns staging-only click rollups:

- total click count
- product vs affiliate click counts
- top offers
- top merchants
- recent click events

`GET /admin/affiliate/recommendation-traces` returns staging-only recommendation audit events:

- total trace count
- recent trace events
- persisted strategy, rule, parser, ranker, and fixture versions per trace
- raw and parsed intent
- recommended offer IDs
- deterministic evaluation trace steps

The staging web app exposes this through the admin-only trace viewer and the proxy endpoint
`POST /api/admin/recommendation-traces`.

`GET /admin/affiliate/recommendation-evaluation` runs the deterministic recommendation fixture
suite against an isolated in-memory database and returns:

- overall status
- pass/fail counts
- case IDs and intents
- first expected source record and merchant
- required and observed trace steps

The staging web app exposes this through the admin-only evaluation panel and the proxy endpoint
`POST /api/admin/recommendation-evaluation`.

`GET /admin/affiliate/recommendation-feedback` returns staging-only quality feedback:

- total feedback count
- Helpful and Not helpful counts
- helpful rate and trace feedback coverage rate
- recent feedback records with trace ID, offer, source, provider, and market

The staging web app exposes this through the admin-only feedback dashboard, the quality-loop refresh
control, and the proxy endpoint `POST /api/admin/recommendation-feedback`.

`POST /admin/affiliate/recommendation-quality/retention` previews or prunes staging-only
recommendation traces and feedback. It defaults to dry-run mode and keeps the latest 50 traces unless
`keep_latest_traces` is supplied. Destructive pruning requires:

```json
{
  "dry_run": false,
  "keep_latest_traces": 50,
  "confirm": "DELETE_STAGING_QUALITY_EVENTS"
}
```

The staging web app exposes this through the feedback dashboard retention controls and the proxy
endpoint `POST /api/admin/recommendation-quality-retention`.

`GET /admin/affiliate/recommendation-quality/export` returns a staging-only JSON quality report:

- report version, export timestamp, and environment
- staging summary counts and latest sync status
- deterministic recommendation evaluation summary
- recommendation feedback summary
- recent recommendation traces
- dry-run retention preview using the latest 10 traces

The report is intended for audit snapshots before pruning quality events or changing ranking logic.
It does not include admin tokens. The staging web app exposes this through the quality cockpit export
button and proxy endpoint `POST /api/admin/recommendation-quality-export`.

`GET /admin/affiliate/llm-parser-status` returns parser enablement metadata for Gate 5E:

- feature flag status
- parser mode
- OpenAI key configured boolean
- active and fallback parser versions
- live-parser readiness
- staging-safe default status
- guardrails and required enablement steps

It does not return API keys, admin tokens, prompts, or model responses. The staging web app exposes
the same data through `POST /api/admin/llm-parser-status`.

`GET /admin/affiliate/staging-summary` returns staging operations state:

- normalized product, listing, offer, coupon, cashback, click, recommendation trace, sync job, and
  sync error counts
- latest mock sync job status and ingest counters
- recent sync errors for quick debugging

Use `make staging-smoke` with `ADMIN_API_TOKEN` set to run the live staging API and web proxy smoke
suite after each deploy.

## OpenAPI

FastAPI publishes the generated OpenAPI schema at `/openapi.json` and interactive docs at `/docs`.
