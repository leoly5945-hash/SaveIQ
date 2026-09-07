# Decision Engine (CP9–CP11)

`app/services/decision/` — deterministic commerce decision logic. Given a price
history series and a current price it produces trailing-window statistics, an
effective price, a 0–100 score, and a **BUY / WAIT / FAIR / UNKNOWN** verdict with
plain-language reasons.

Everything here is **pure and deterministic**. There is no ML, no learned
weights, and **no input for merchant commission or affiliate payout anywhere in
the scoring path** — a higher-paying merchant cannot earn a better score because
there is nowhere to express that (spec §24).

## Step-function history (Keepa)

Keepa records a point only when the price **changes**. A product whose price has
been flat for months therefore has *no* raw points in a recent window even though
its price is perfectly known. `KeepaProvider._parse_history` handles this before
the engine sees it:

* it decodes the full change-point history for the deepest of the AMAZON / NEW /
  BUY_BOX series (`base_kind`),
* forward-fills it to **one point per day** across the requested window
  (`_densify_daily`),
* and carries through Keepa's own `avg30/avg90/avg180` + `min/max` as
  `metadata.keepa_stats`, plus `source_observations` (real changes in the window)
  and `lifetime_observations` (changes over the whole tracked history).

So `PriceIntelligence.total_points` is a dense daily count; **confidence and the
thin-data gate use `source_observations` / `lifetime_observations` instead**, and
the score prefers `provider_stats` over the windowed numbers when present.

## CP9 — price intelligence (`price_intelligence.py`)

`summarize_points(points, *, currency, current_cents=None, prefer_kind=None,
windows=(7,30,90,180), now=None, source_observations=None,
lifetime_observations=None, provider_stats=None) -> PriceIntelligence`

* Selects one coherent series from mixed-kind points. `prefer_kind` wins if it
  has points (the orchestrator passes the kind matching the current price's
  basis, e.g. `buy_box`); otherwise `buy_box → amazon → new → used`.
* Per window: `sample_count`, `min` / `max` / `avg` / `median` cents.
* Derived signals:
  * `current_percentile_90d` — fraction of 90-day observations **strictly
    cheaper** than current. `0.0` = nothing was cheaper (best price seen).
  * `is_all_time_low` — current ≤ all-time min + 0.5 %.
  * `days_since_price_this_low` — calendar days since the series was last ≤
    current.
  * `times_this_low_90d` — 90-day observations within 2 % of current.
* `coverage_days` — span from first to last observation.

`summarize_history(history, …)` wraps it for a `ProviderPriceHistory`.

## CP10 — effective price (`effective_price.py`)

`compute_effective_price(base_price_cents, *, currency, shipping_cents=0,
extra_components=None) -> EffectivePrice`

What the shopper actually pays: `base + shipping + Σ components`. Components are
signed (`amount_cents` negative for a coupon) and must only be things the shopper
is **guaranteed** to get. Never uses a merchant's strike-through "list price".
For the Keepa / Amazon MVP this is just `base + shipping`.

`effective_price_from_provider(price, *, offer=None)` folds in an offer's
shipping.

## CP11 — deal score (`deal_score.py`)

`score_deal(effective_price, intelligence) -> DealAssessment`

**Score** (0–100, higher = better time to buy):

1. No usable 90-day band (no window samples **and** no `provider_stats`), or
   degenerate numbers → `UNKNOWN`, score 50, confidence `low`. No pretend verdict.
2. Flat window (`min90 == max90`) → `FAIR` at score 55 with the reason "the price
   has held at $X for 90 days — no recent dips to wait for" (or `WAIT` at 40 if
   the effective price is above that standing price). No dip exists to score.
3. Otherwise start at 50. `score += 250 × (avg90 − effective) / avg90` — i.e.
   +2.5 points per 1 % below the 90-day average, symmetric.
4. `+15` if effective ≤ 90-day low × 1.02.
5. `+10` if `is_all_time_low`.
6. `−15` if effective ≥ 90-day high × 0.98.
7. Clamp to 0–100.

The 90-day `avg` / `min` / `max` come from `provider_stats` when the provider
computed them (Keepa does), else from the densified window.

**Verdict:**

| condition | verdict |
| --- | --- |
| score ≥ 70 **and** effective ≤ 90-day low × 1.05 | `BUY` |
| score ≤ 36 **or** effective ≥ 90-day avg × 1.15 | `WAIT` |
| otherwise | `FAIR` |

**Confidence** (based on real price *changes*, not densified points):

| confidence | needs |
| --- | --- |
| `high` | ≥ 60 coverage days **and** (≥ 8 recent changes **or** ≥ 40 lifetime changes) |
| `medium` | ≥ 21 coverage days **and** (≥ 3 recent changes **or** ≥ 15 lifetime changes) |
| `low` | otherwise |

`recent` = `source_observations` (falls back to `total_points` when the provider
gives no change count); `lifetime` = `lifetime_observations`.

Every rule that fires appends a human `reason` string.

## Orchestrator (`assess.py`)

`assess_from_provider(price: ProviderPrice, history: ProviderPriceHistory, *,
offer=None, now=None) -> DealAssessment | None`

CP10 → CP9 (series kind chosen from `price.source`) → CP11. Returns `None` only
when there is no current price at all.

## CP6 — URL → product reference (`app/services/product_url.py`)

`extract_product_ref(raw, *, follow_redirects=False) -> ExtractedProductRef | None`

Parses an Amazon URL — `/dp/…`, `/gp/product/…`, `/gp/aw/d/…`, `/-/en/dp/…`,
`?asin=` / `?pd_rd_i=` — or a bare 10-char ASIN, into `{retailer, market,
product_id, keepa_domain, source_url}`. TLD picks the market (`.ca` → CA / Keepa
domain 6). `amzn.to` / `a.co` short links resolve only when `follow_redirects` is
set (one HEAD, no body). Non-Amazon hosts and search/listing pages return `None`.

## Endpoints

The flow `(url | product_id) → provider fetch → engine` lives in
`app/services/decision/price_check.py::run_price_check` and is shared by:

| endpoint | auth | notes |
| --- | --- | --- |
| `GET /check?url=…` or `?product_id=…` | **public** (CP16) | per-IP rate limited (`CHECK_RATE_PER_MINUTE`, only when `RATE_LIMIT_ENABLED`); each call spends a provider token |
| `GET /admin/providers/price-check` | admin | same, plus `debug=1` for the raw provider shape |

Both take optional `days=` (7–365). A non-`.ca` marketplace URL is rejected with
422 until a provider covers it.

`POST /alerts` (public, `ALERT_CREATE_RATE_PER_MINUTE`) creates a tracked product
+ one observation + a price alert in the same call (see `docs/PRICE_ALERTS.md`).

## Not yet

* Persistence — the engine reads a series it is handed; storing provider-sourced
  observations into `price_history` and polling on a schedule is CP15.
* Coupons / cashback components — the hook exists (`extra_components`), no source
  feeds it for Amazon.
