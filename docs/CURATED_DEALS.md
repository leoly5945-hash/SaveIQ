# Curated deal set

A small set of **real, hand-picked products** that gives the site something
concrete to show (search + a homepage "Featured deals" strip) instead of an
empty search box. This is what affiliate-network reviewers and early visitors
actually see, so everything here must be true: real products, real point-in-time
prices, **no invented discounts or "lowest price" claims**.

## Where the data lives

`apps/api/app/services/affiliate/curated_deals.json` — version-controlled, inside
the API image (the repo-root `data/` dir is `.dockerignore`d, so it can't live
there). Each row:

```json
{
  "asin": "B088NRLMPV",
  "title": "Anker USB-C to USB-C Cable, 60W, 6 ft",
  "brand": "Anker",
  "category": "Electronics",
  "category_slug": "electronics",
  "price_cents": 1699,
  "price_checked": "2026-08-29",
  "blurb": "Short, factual one-liner. No hype, no discount claims."
}
```

Retailer/currency/market are file-level (`Amazon.ca` / `CAD` / `CA`).

## How it flows

1. **`CuratedAmazonProvider`** (`curated_provider.py`, `source = "amazon_ca"`)
   turns each row into a normalized product offer. The affiliate URL is
   `https://www.amazon.ca/dp/<ASIN>?tag=<AMAZON_ASSOCIATE_TAG>`
   (`AMAZON_ASSOCIATE_TAG` defaults to `saveiq-20`).
2. **`POST /admin/affiliate/sync/curated`** (admin token) runs it through the
   normal ingestion pipeline into `merchants` / `canonical_products` /
   `merchant_listings` / `offers` / `affiliate_links`. Idempotent: re-running
   refreshes prices/titles in place; a byte-identical re-run is a no-op.
3. The offers show up in **`/search`** like any other offer, and in a dedicated
   **`GET /featured-deals`** read model (`provider_source = "amazon_ca"`,
   cheapest first) that the homepage `FeaturedDeals` component renders. Each card
   shows the price, the `price_checked` date ("confirm at Amazon.ca"), and the
   Amazon Associate disclosure.
4. **`GET /go/<offer_id>?t=affiliate`** logs the click server-side and redirects
   to the tagged Amazon URL with a per-click `ascsubtag` SubID appended, exactly
   like every other affiliate click (see `AFFILIATE_ATTRIBUTION.md`).

## Running the sync

```bash
ADMIN_API_TOKEN=... python scripts/seed_curated_deals.py \
  --api-url https://dealhunter-production-api.onrender.com
```

The script POSTs the sync and then asserts `/featured-deals` returns at least
one deal.

## Adding or refreshing deals

1. Find the product on amazon.ca, take the **ASIN** from the `/dp/<ASIN>` URL and
   the **current price**.
2. Add / edit the row in `curated_deals.json`. Bump `price_checked` to the date
   you actually looked. Only ever record the price a normal shopper pays — no
   "was" price.
3. Merge, let the image build, then re-run `seed_curated_deals.py` against the
   target environment.

## Swapping to affiliate deep links

Right now the outbound URL is the plain Amazon product URL plus our Associates
tag. When another network (Skimlinks, Sovrn, …) is approved and a retailer is
better monetised through it, update `affiliate_links.url` for that merchant — the
`/go` redirect and reconciliation keep working unchanged.
