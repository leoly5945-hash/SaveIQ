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
