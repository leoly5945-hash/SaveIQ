# API

The public API currently exposes health, mock search, offer detail, and mock click tracking
endpoints.
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

Admin responses expose normalized operational data and do not expose provider secrets or full raw
payloads.

`GET /admin/affiliate/click-analytics` returns staging-only click rollups:

- total click count
- product vs affiliate click counts
- top offers
- top merchants
- recent click events

## OpenAPI

FastAPI publishes the generated OpenAPI schema at `/openapi.json` and interactive docs at `/docs`.
