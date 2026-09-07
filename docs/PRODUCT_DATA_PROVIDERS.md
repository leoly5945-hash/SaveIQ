# Product Data Providers (CP4)

A **product data provider** is a read-side adapter over an external source of
product, offer and price data. It is what the URL price-checker (CP6), the
decision engine (CP9–CP11) and scheduled price polling call when they need a
current price, a live offer list, or a price history for a product.

This is **not** the affiliate ingestion pipeline. `app/services/affiliate/`
(`AffiliateProviderAdapter`) is a batch job that pulls a feed and *writes*
`merchant_listings` / `offers` / `price_history`. Providers here are queried on
demand and **never touch the database** — the caller decides what to persist.

## The interface

`app/providers/base.py` — `ProductDataProvider` (a `runtime_checkable`
`Protocol`):

| method | returns | notes |
| --- | --- | --- |
| `is_configured()` | `bool` | has credentials for live calls |
| `search_products(query, *, limit=10)` | `list[ProviderProduct]` | best match first |
| `get_product(id)` | `ProviderProduct \| None` | `None` when the source has no such id |
| `get_offers(id)` | `list[ProviderOffer]` | every buyable offer we can see |
| `get_price(id)` | `ProviderPrice \| None` | the single current effective price |
| `get_price_history(id, *, days=180)` | `ProviderPriceHistory \| None` | when the source keeps history |

Each provider also exposes `name`, `market`, `currency`, and
`capabilities: frozenset[ProviderCapability]`. Callers check
`ProviderCapability.price_history in provider.capabilities` before dispatching, so
a thin source never has to raise `NotImplementedError`.

Failure model:

* operational failure (transport, auth, quota) → raise `ProviderError`
* "this source simply doesn't have that product" → return `None` / `[]`, or raise
  `ProviderProductNotFound` (a `ProviderError` subclass callers may catch as an
  empty result)

`ProviderPrice.list_price_cents` is the merchant's **stated** list / RRP when the
source reports one. It is never a computed "was" price and must not be turned
into a discount percentage — the decision engine derives cheap/expensive from
observed history, not from a merchant's strike-through claim.

## The registry

`app/providers/registry.py`:

* `ProviderRegistry` — `register` / `get` / `try_get` / `list` / `names` /
  `with_capability`.
* `build_default_registry(settings)` — registers every provider that is
  **configured**. A provider whose credentials are absent is skipped, not
  registered broken. An empty registry is a valid state.
* `get_provider_registry()` — the process-wide default, built once from
  `get_settings()`. `reset_provider_registry_for_tests()` clears it.

`GET /admin/providers` (admin token) lists what is registered and whether each is
configured — the deploy-time check that `KEEPA_API_KEY` is wired.

## Keepa provider

`app/providers/keepa.py` — `KeepaProvider`. Amazon catalogue + multi-year price
history via the [Keepa API](https://keepa.com/#!api). One marketplace per
instance via `domain` (`6` = Amazon.ca → market `CA`, currency `CAD`).

### Config

| env | default | meaning |
| --- | --- | --- |
| `KEEPA_API_KEY` | *(unset)* | pay-as-you-go API key. Unset → provider not registered. `sync: false`, never committed. |
| `KEEPA_DOMAIN` | `6` | Keepa domain id. `6` = Amazon.ca. |
| `KEEPA_TIMEOUT_SECONDS` | `20.0` | per-request timeout. |

### What one call returns

`get_price` / `get_offers` / `get_price_history` each make **one** `/product`
call (`history=1`, plus `stats=<days>` / `offers=20` / `buybox=1` as needed):

* current price — buy box → Amazon → marketplace-new, first available wins;
  `source` records which (`keepa:buy_box` etc.)
* live third-party offers with condition, shipping, FBA/Prime flags, buy-box flag
  (`get_offers`; when Keepa returns no offer array, one offer is synthesised from
  the current price)
* price history — Amazon / New / Used / Buy-Box series, decoded from Keepa's
  `csv` arrays, filtered to the trailing `days`; Keepa's own `avg30` / `avg90` /
  `min` / `max` are stashed in `metadata.keepa_stats` as a cross-check for CP9

Keepa gives **current** data plus history it already holds. Ongoing daily
observations still come from scheduled polling (CP15 worker) appended on top.

### Token cost (rough, verify against the dashboard)

* `/product` ≈ 1 token + ~6 with `offers`; history is free
* `/search` ≈ 10 tokens
* backfilling the ~68 seed ASINs with full history ≈ a few hundred tokens
* ~100 products polled once/day ≈ 3,000 tokens/month ≈ well inside the entry plan

### ToS

Keepa's API is sold for commercial use and price-tracking tools built on it are
common. Do not resell the raw data feed or rebuild keepa.com. Showing a chart +
verdict for a product a user looked up is within normal use.

## Adding a provider

1. New module in `app/providers/` implementing `ProductDataProvider` (a plain
   class — the `Protocol` is structural, no base class to inherit).
2. Declare `capabilities` honestly.
3. Register it in `build_default_registry()` behind its own config check.
4. Unit-test with a fake transport and **synthetic** responses — no live calls in
   CI.

The next planned provider is a Google Shopping data vendor (e.g. DataForSEO) for
multi-merchant comparison, behind this same interface.
