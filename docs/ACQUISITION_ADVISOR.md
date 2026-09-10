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
| `tco.py` | `compute_tco(option, profile) -> TCOBreakdown` — places every payment on a month index, discounts to present value when the buyer sets `annual_discount_rate`, credits resale value still held at the horizon |
| `compare.py` | `compare_paths(options, profile) -> PathRecommendation` — ranks by `effective_total_cents` (lower = better) and emits plain-language `caveats` + a fixed `verify_first` list |
| `catalog.py` + `acquisition_catalog.json` | hand-maintained option sets per product; a non-engineer edits the JSON |

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

* `GET /admin/acquisition/catalog` — seeded products + option counts + the
  data disclaimer
* `GET /admin/acquisition/compare?slug=<slug>&horizon_months=&annual_discount_rate=&upgrades_every_months=&is_business=&service_sensitivity=`
  — the ranked comparison for one product and buyer profile

## The catalogue is ILLUSTRATIVE

`acquisition_catalog.json` currently holds **one** worked example
(`iphone-17-pro-256gb`, 4 options) with rough Canadian-market estimates entered
to exercise the engine. Every option carries `verify: true` and its own `as_of`
date, and the file's top-level `disclaimer` says so. Do not present these numbers
to a user as fact until an operator has confirmed each one. Adding real products
and carrier plan data is the next data task.
