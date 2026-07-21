# API

The public API currently exposes health only. Development/admin affiliate endpoints are protected by
the `X-Admin-Token` header and are intended for local or staging visibility.

## Public

`GET /health`

```json
{
  "status": "ok",
  "service": "DealHunter API",
  "version": "0.1.0"
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
- `sort`: `price_asc`, `price_desc`, or `merchant`; default `price_asc`.
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
      "match_reasons": ["product title", "offer title"]
    }
  ]
}
```

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

Admin responses expose normalized operational data and do not expose provider secrets or full raw
payloads.

## OpenAPI

FastAPI publishes the generated OpenAPI schema at `/openapi.json` and interactive docs at `/docs`.
