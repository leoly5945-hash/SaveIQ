# Affiliate Connectors

Affiliate connectors are provider plugins. Provider-specific code stays behind the adapter protocol
in `app.services.affiliate`, while core product, listing, offer, coupon, cashback, and ingestion
logic remains provider-neutral.

## Adapter Operations

Adapters may implement:

- `test_connection`
- `fetch_merchants`
- `fetch_products`
- `fetch_offers`
- `fetch_prices`
- `fetch_coupons`
- `fetch_cashback`
- `fetch_incremental_updates`
- `validate_record`
- `normalize_record`

All connector inputs and outputs use typed Pydantic schemas.

## Mock Provider

The current provider is `mock_ca`, a deterministic Canadian fixture feed using CAD. It includes
three merchants, five canonical products, multiple merchant listings for the same product, current
offers, price observations, valid and expired coupons, cashback, a duplicate record, a malformed
record, and a stale record.

## Guardrails

- No real affiliate integrations yet.
- No web scraping.
- No provider secrets in source or docs.
- No raw sensitive payloads returned through admin APIs.
- Future providers should be added by registering a new adapter, not by changing core domain logic.
