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
      "step": "parse_intent",
      "input": "Find fresh wireless earbuds with a coupon",
      "output": "query='wireless earbuds', has_coupon=True, has_cashback=None, freshness=fresh, sort=price_asc",
      "notes": ["rule-based parser", "no model call"]
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
        "deterministic mock strategy"
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
- recent feedback records with trace ID, offer, source, provider, and market

The staging web app exposes this through the admin-only feedback panel and the proxy endpoint
`POST /api/admin/recommendation-feedback`.

`GET /admin/affiliate/staging-summary` returns staging operations state:

- normalized product, listing, offer, coupon, cashback, click, recommendation trace, sync job, and
  sync error counts
- latest mock sync job status and ingest counters
- recent sync errors for quick debugging

Use `make staging-smoke` with `ADMIN_API_TOKEN` set to run the live staging API and web proxy smoke
suite after each deploy.

## OpenAPI

FastAPI publishes the generated OpenAPI schema at `/openapi.json` and interactive docs at `/docs`.
