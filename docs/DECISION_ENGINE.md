# Decision Engine (CP9–CP11)

`app/services/decision/` — deterministic commerce decision logic. Given a price
history series and a current price it produces trailing-window statistics, an
effective price, a 0–100 score, and a **BUY / WAIT / FAIR / UNKNOWN** verdict with
plain-language reasons.

Everything here is **pure and deterministic**. There is no ML, no learned
weights, and **no input for merchant commission or affiliate payout anywhere in
the scoring path** — a higher-paying merchant cannot earn a better score because
there is nowhere to express that (spec §24).

## CP9 — price intelligence (`price_intelligence.py`)

`summarize_points(points, *, currency, current_cents=None, prefer_kind=None,
windows=(7,30,90,180), now=None) -> PriceIntelligence`

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

1. Thin history (90-day window has < 3 samples, or no avg/min) → `UNKNOWN`,
   score 50, confidence `low`. No pretend verdict.
2. Start at 50. `score += 250 × (avg90 − effective) / avg90` — i.e. +2.5 points
   per 1 % below the 90-day average, symmetric.
3. `+15` if effective ≤ 90-day low × 1.02.
4. `+10` if `is_all_time_low`.
5. `−15` if effective ≥ 90-day high × 0.98.
6. Clamp to 0–100.

**Verdict:**

| condition | verdict |
| --- | --- |
| score ≥ 70 **and** effective ≤ 90-day low × 1.05 | `BUY` |
| score ≤ 36 **or** effective ≥ 90-day avg × 1.15 | `WAIT` |
| otherwise | `FAIR` |

**Confidence** (Keepa records a point per price *change*, so coverage matters
more than raw count):

| confidence | needs |
| --- | --- |
| `high` | ≥ 60 coverage days **and** ≥ 8 points |
| `medium` | ≥ 21 coverage days **and** ≥ 4 points |
| `low` | otherwise |

Every rule that fires appends a human `reason` string.

## Orchestrator (`assess.py`)

`assess_from_provider(price: ProviderPrice, history: ProviderPriceHistory, *,
offer=None, now=None) -> DealAssessment | None`

CP10 → CP9 (series kind chosen from `price.source`) → CP11. Returns `None` only
when there is no current price at all.

## Trying it

`GET /admin/providers/price-check?product_id=<ASIN>[&provider=keepa][&days=90]`
(admin token) live-fetches from a provider and returns a full `DealAssessment`.
This is the staging surface until the public price-checker UI (CP16) lands. Each
call spends provider tokens (Keepa: ~1 `/product` call).

## Not yet

* Persistence — the engine reads a series it is handed; storing provider-sourced
  observations into `price_history` and polling on a schedule is CP15.
* Coupons / cashback components — the hook exists (`extra_components`), no source
  feeds it for Amazon.
