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

## DataForSEO provider

`app/providers/dataforseo.py` — `DataForSEOProvider`. Cross-merchant offers via
DataForSEO's Google Shopping product data (`/v3/merchant/google/products/...`).
**Query-based**, not id-based: the keyword is the product title we got from Keepa,
trimmed of marketing fluff (`comparison_cache.shopping_keyword`).

DataForSEO's Google Shopping is **task-based — there is no live endpoint**. You
`task_post` a keyword (charged), wait, then `task_get/advanced/{id}` the result.
So it cannot answer inside a synchronous price-check:

* `submit_offers_task(keyword) -> task_id` / `fetch_offers_task(task_id)` — the
  split calls the comparison cache drives.
* `get_offers` / `get_price` / `search_products` — submit + short poll
  (`_SYNC_POLL_ATTEMPTS` × `_SYNC_POLL_DELAY_SECONDS`). Admin/debug only; the
  price-check path never calls them.

`run_price_check` reads the **comparison cache**
(`app/services/decision/comparison_cache.py`, table `merchant_comparisons`):
the first check of a cold product returns no comparison and posts a task; a later
check (≥20s on) or the alert cron polls it and stores the raw offers; every
check after that renders the comparison from cache (CP7 matching re-runs on each
read so "cheaper?" stays correct as the Amazon price moves). Ready rows live 24h.
Any failure is swallowed — the verdict + sparkline always work.

Capabilities: `search`, `get_offers`, `get_price` — **no** `price_history`.

| env | default | meaning |
| --- | --- | --- |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | *(unset)* | Basic-auth pair (`LOGIN` = account email, `PASSWORD` = the **API password** from app.dataforseo.com/api-access, not the Base64 string). Unset → provider not registered, checks stay Amazon-only. `sync: false`. |
| `DATAFORSEO_LOCATION_CODE` | `2124` | `2124` = Canada. |
| `DATAFORSEO_LANGUAGE_CODE` | `en` | |
| `DATAFORSEO_TIMEOUT_SECONDS` | `25.0` | per HTTP call. |

Cost: `task_post` is ~$0.0012/result + a small per-request fee — one per distinct
product per 24h (the cache TTL), not one per check.

`POST /admin/providers/comparison-poll` (admin) advances every in-flight task on
demand; `run_alert_cycle` also sweeps them once a day as a backstop.

## Adding a provider

1. New module in `app/providers/` implementing `ProductDataProvider` (a plain
   class — the `Protocol` is structural, no base class to inherit).
2. Declare `capabilities` honestly.
3. Register it in `build_default_registry()` behind its own config check.
4. Unit-test with a fake transport and **synthetic** responses — no live calls in
   CI.

The next planned provider is a Google Shopping data vendor (e.g. DataForSEO) for
multi-merchant comparison, behind this same interface.
