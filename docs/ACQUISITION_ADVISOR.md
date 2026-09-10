# Acquisition Advisor (Layer 2)

SaveIQ's price engine (`app/services/decision/`) answers *"is this price good
versus its history"*. The acquisition advisor answers the question a smart shopper
asks next: **which way of getting this product is best for me** — buy outright,
0% financing, a bring-it-back lease, a device+plan bundle, or last-gen/refurb.

It is the "price checker → shopping advisor" step. Deterministic and transparent,
exactly like the price verdict: every cash flow is shown, every profile-driven
warning is spelled out, and there is nowhere to express a merchant payout. An LLM
layer (Layer 3) will pick which options apply to a natural-language query and
narrate the result — it does **not** do the arithmetic here.

## The pieces

`app/services/acquisition/`

| module | what it holds |
| --- | --- |
| `models.py` | `AcquisitionKind` (retail / financing / lease / bundle / refurb), `AcquisitionOption` (one option's cash flows), `BuyerProfile` (horizon, cash discount rate, upgrade cadence, ownership pref, service sensitivity, business flag) |
| `catalog.py` + `data/*.json` | the small **category/channel** rulesets (not per-product): `programs.json` (~7 acquisition programs), `carrier_plans.json` (~4 Canadian plan price points), `depreciation.json` (resale curves by category/age), `demo_products.json` (a few reference products for the `?slug=` path) |
| `composer.py` | `compose_options(ProductContext) -> list[AcquisitionOption]` — turns retail price + category + brand into concrete option rows by matching the applicable programs |
| `tco.py` | `compute_tco(option, profile) -> TCOBreakdown` — places every payment on a month index, discounts to present value when the buyer sets `annual_discount_rate`, credits resale value still held at the horizon |
| `compare.py` | `compare_paths(options, profile) -> PathRecommendation` — ranks by `effective_total_cents` (lower = better) and emits plain-language `caveats` + a fixed `verify_first` list |

### Why composition, not a per-product table

Acquisition structures are **not** per product — there are millions of SKUs but
only a handful of ways to pay for one. Carrier financing / bring-it-back apply to
phones and cellular devices; retailer 0% financing to TVs, appliances, furniture
over a price floor; refurb to whole channels at a formula discount; "buy outright
+ resale" to everything. So the data is ~7 program rulesets + ~4 plan rows + ~10
depreciation curves — a few hundred lines a non-engineer keeps current — and the
composer assembles the options for any product from its price + category + brand.
A product matching no special program still gets "buy outright"; the advisor
always has an answer. A plan-cost line only attaches to carrier-eligible devices
(a phone needs service however you got the handset; a TV does not).

## TCO model

For horizon `H` and monthly rate `m = annual_discount_rate / 12`, the present
value of a payment `amt` at month `k` is `amt / (1+m)**k` (upfront is `k=0`):

* **upfront** — retail's full price, or a financing/lease down payment
* **device installments** — `device_monthly_cents` for `k = 1..min(term, H)`; if
  `term > H` the remaining balance is counted as settled at month `H`
* **lease residual** — if `returns_at_term` and the buyer upgrades within
  `term + 3` months → modelled as a **return** (residual not paid, nothing owned);
  otherwise → residual paid at `term`, device kept
* **plan** — `(plan_monthly - credit)` while the credit lasts, then full price
* **resale** — value still owned at `min(resale_at_months, H)`, subtracted

`nominal_total_cents` is the plain sum; `effective_total_cents` is the discounted
version; `monthly_equivalent_cents` divides that by the horizon.

## Caveats (transparent, never a silent reweight)

`compare_paths` fires these when they apply: cheapest path leaves you owning
nothing; a lease/return option was considered but you hold devices too long for
it; the recommended path has lock-in; a service-sensitive buyer's cheapest path
rides a discount/BYOD carrier; a business buyer should weigh the priority-support
tier; the top two paths are within a small margin so the decision isn't about
money. `verify_first` always carries the things SaveIQ structurally cannot know
(current device price per seller, real "unlimited" throttle thresholds, 5G at
your address).

## Admin surface

* `GET /admin/acquisition/data` — the loaded rulesets (programs, plans,
  depreciation categories, demo slugs) + the data disclaimer
* `GET /admin/acquisition/compare?slug=<demo-slug>&…` **or**
  `?retail_price_cents=&category=&brand=&tier=&carrier_eligible=&…`
  plus the buyer profile (`horizon_months`, `annual_discount_rate`,
  `upgrades_every_months`, `is_business`, `service_sensitivity`) — the ranked
  comparison. The real integration passes price + category from the price layer.

## The data is ESTIMATED

`programs.json` / `carrier_plans.json` / `depreciation.json` hold best-effort
figures from public reporting (Apple.ca, carrier/retailer pages, planhub /
mobilesyrup / iphoneincanada, Sept 2026). Each file carries a disclaimer and
every composed option is tagged `verify: true` with an `as_of` date. Terms move
monthly — refresh before showing a user a number. Populating real, dated values
is a lightweight recurring data task (not code): ~7 program rows, ~4 plan rows,
~10 curves.
