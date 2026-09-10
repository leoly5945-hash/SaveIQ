# Decisions

## 2026-07-10: Use Modular Monolith

Status: Accepted

DealHunter starts as a modular monolith with clear internal package boundaries. This reduces
operational overhead while the product surface and data model are still forming.

## 2026-07-10: Use PostgreSQL With pgvector

Status: Accepted

PostgreSQL is the primary store and pgvector is enabled for future semantic retrieval. Vector fields
remain optional until the AI retrieval system is implemented.

## 2026-07-10: No Web Scraping

Status: Accepted

DealHunter will use approved APIs, feeds, or partner data access. Web scraping is outside the
intended architecture.

## 2026-07-18: Rename To DealHunter AI

Status: Accepted

The public product brand is DealHunter AI. Public branding is now exposed through configuration
where practical.

## 2026-07-18: Affiliate Connectors Are Provider Plugins

Status: Accepted

Future affiliate integrations should implement the provider adapter protocol and register with the
provider registry. Provider mapping must remain isolated from core product and offer logic.

## 2026-07-18: Deterministic Matching Only

Status: Accepted

Product resolution uses exact identifiers and brand plus MPN matching. LLM-based matching is deferred
until evaluation and review workflows exist.

## 2026-07-24: Gate 4A Uses Rule-Based Recommendations

Status: Accepted

The first recommendation surface is a deterministic skeleton that reuses normalized stored search
data and returns an inline evaluation trace. It intentionally avoids LLM calls, real affiliate
integrations, web scraping, personalization, and persisted trace storage until evaluation criteria
and production guardrails are defined.

## 2026-07-24: Gate 4B Recommendation Evaluation Is Offline

Status: Accepted

Recommendation evaluation fixtures run against a temporary in-memory database seeded from the mock
provider. This keeps regression checks deterministic, cheap, and safe while the project has no real
affiliate connectors, user personalization, or LLM orchestration.

## 2026-07-25: Gate 4C Persists Recommendation Traces Without User Identity

Status: Accepted

Each recommendation request writes a `recommendation_trace_events` row containing the deterministic
strategy, raw intent, parsed intent, result count, recommended offer IDs, and trace steps. The trace
store is admin-only staging audit scaffolding and intentionally excludes user identity, IP address,
tokens, real affiliate payloads, and model prompts or responses.

## 2026-07-25: Gate 4D Trace Viewer Is Staging Admin Only

Status: Accepted

The first trace viewer lives inside the staging UI admin area and reads from the existing
admin-protected recommendation trace proxy. It is intentionally read-only and does not expose traces
without the staging admin token.

## 2026-07-25: Gate 4E Evaluation Runs Against Isolated Fixtures

Status: Accepted

The staging evaluation panel runs the deterministic recommendation fixtures against an isolated
in-memory database seeded from the mock provider. This gives admins a low-cost pass/fail quality
signal without mutating staging data, calling external affiliate systems, or invoking an LLM.

## 2026-07-25: Gate 4F Explanations Are Deterministic

Status: Accepted

Recommendation explanations are composed from parsed intent fields, search match reasons, ranking
reasons, and fixed guardrails. This keeps staging explainability inspectable without creating a new
LLM dependency, scraping behavior, or live affiliate-network integration.

## 2026-07-25: Gate 4G Feedback Stores Quality Signals Without Identity

Status: Accepted

Recommendation feedback stores trace ID, offer ID, rating, source, provider source, market, and
timestamp. It does not store user identity or session fingerprints. This gives staging a lightweight
quality loop while keeping privacy and production-readiness risks low.

## 2026-07-25: Gate 4H Feedback Dashboard Is Staging-Only

Status: Accepted

The feedback dashboard aggregates Helpful rate and trace feedback coverage from stored staging
events. It helps reviewers inspect recommendation quality before any LLM layer exists. It does not
train a model, store identity, or send feedback to external services.

## 2026-07-25: Gate 4L Retention Requires Dry-Run And Confirm

Status: Accepted

Recommendation quality retention is limited to staging trace and feedback events. It defaults to
dry-run previews and requires the explicit `DELETE_STAGING_QUALITY_EVENTS` confirmation phrase before
deleting old events. This keeps staging data bounded while avoiding accidental deletion of normalized
offers, click analytics, or sync history.

## 2026-07-26: Gate 4M Quality Cockpit Stays Web-Only

Status: Accepted

The recommendation quality cockpit is a staging web aggregation of existing evaluation, feedback,
trace, staging summary, and retention-preview data. It does not add a backend aggregate endpoint yet
because the existing admin proxies already provide the needed signals. This keeps the gate small,
cost-neutral, and mock-only while making quality review easier for non-terminal staging checks.

## 2026-07-26: Gate 4N Quality Export Is Snapshot-Only

Status: Accepted

The recommendation quality export is a staging-only JSON snapshot that combines existing evaluation,
feedback, trace, staging summary, and dry-run retention data. It exists to preserve review evidence
before pruning or ranking-rule changes. The export avoids admin tokens, user identity, live AI
outputs, scraping data, and real affiliate-network data.

## 2026-07-27: Gate 4O Versions Rules Before AI Changes

Status: Accepted

Recommendation strategy, rule set, intent parser, ranker, and fixture set versions are centralized
and surfaced through recommendation responses, evaluation summaries, trace admin responses, quality
exports, staging UI, and smoke checks. This gives staging a stable audit marker before future ranking
or AI changes. The current database trace row still stores only the strategy; per-trace rule-version
columns are deferred until historical production trace semantics are needed.

## 2026-07-27: Gate 4P Persists Version Metadata Per Trace

Status: Accepted

Recommendation trace rows now store rule, parser, ranker, and fixture versions alongside the
strategy. Existing staging rows are backfilled to the Gate 4O metadata by migration. This makes trace
audits historical instead of only comparing against current metadata, while still avoiding user
identity, live AI payloads, scraping output, or real affiliate-network data.

## 2026-07-27: Gate 4Q Keeps Trace Drilldown UI-Only

Status: Accepted

The recommendation trace drilldown is built in the staging web UI from existing trace and feedback
summary proxy responses. It intentionally avoids a new backend endpoint because the required row
versions, parsed intent, ranked offer IDs, evaluation steps, and recent feedback are already present
in the admin payloads. This keeps the gate small and avoids expanding staging infrastructure.

## 2026-07-27: Gate 4R Compares Traces Without Expanding the API

Status: Accepted

Trace comparison is implemented client-side from the existing recent trace payload. Comparing
versions, parsed intent, result count, ranked offer IDs, and evaluation step outputs is enough for
staging reviewers to spot ranking changes before the system introduces real AI parsing. A dedicated
compare endpoint is deferred until traces become large enough to need server-side diffing.

## 2026-07-28: Gate 4S Uses a UI Checklist for Phase Readiness

Status: Accepted

Gate 4 closeout readiness is represented as a staging UI checklist instead of a new backend status
endpoint. The cockpit already has all required source data from evaluation, traces, feedback,
retention preview, quality export, and version metadata. Keeping the readiness calculation in the UI
avoids expanding the API before the recommendation quality rules stabilize.

## 2026-07-29: Gate 4T Closes The Deterministic Recommendation Phase

Status: Accepted

Gate 4 is closed with deterministic recommendations, fixture evaluation, persisted traces, version
metadata, explanations, feedback, retention preview, trace comparison, quality export, and staging
smoke coverage. The next phase should prototype LLM intent parsing behind these existing guardrails
rather than introducing a full autonomous agent or real affiliate integrations.

## 2026-07-29: Gate 5A Defines Parser Contract Before Model Calls

Status: Accepted

The LLM intent-parser phase starts with versioned input/output schemas, allowed sort values,
guardrails, and fallback policy before adding OpenAI configuration or model execution. The active
recommendation parser remains deterministic `intent-parser-v0`, and low-confidence, invalid,
misconfigured, or failed LLM parsing must fall back to it. This keeps Gate 5 small, auditable, and
mock-only while preserving the existing evaluation and trace foundation.

## 2026-07-29: Gate 5B Keeps OpenAI Behind An Injected Client

Status: Accepted

OpenAI configuration is added before any live model execution. The LLM parser service accepts an
injected client and falls back unless the feature flag, parser mode, key requirements, schema
validation, and confidence threshold all pass. This lets local tests and future staging checks
exercise the parser boundary with a mock client while avoiding accidental network calls, spend, or
unreviewed model output.

## 2026-07-30: Gate 5C Wires The Parser Behind Fallback

Status: Accepted

The recommendation route now passes runtime settings into the LLM parser service, but the default
configuration still falls back to deterministic `intent-parser-v0`. Route-driven traces include a
parser-gate step so staging can prove why deterministic parsing was used. The mock-enabled parser
path is covered in tests through an injected client, keeping live model calls and OpenAI spend out of
Gate 5C.

## 2026-07-30: Gate 5D Adds Live Parser Only Behind Explicit Controls

Status: Accepted

The first live OpenAI parser client is implemented inside the existing parser service boundary. It
is only attached when the feature flag is enabled, parser mode is `openai`, and `OPENAI_API_KEY` is
configured. The client sends constrained parser input, requests schema-shaped JSON, validates the
response locally, and falls back to `intent-parser-v0` on request errors, invalid JSON, schema
failure, or low confidence. Tests use a fake HTTP transport so CI and staging smoke do not depend on
OpenAI network access or spend.

## 2026-08-04: Gate 5E Closes Parser Enablement With Status Checks

Status: Accepted

The constrained LLM parser phase closes with an admin-only parser status endpoint instead of turning
the model on by default. Staging can now prove that the live parser is either safely disabled or
explicitly ready through feature flag, mode, and secret presence checks. The endpoint returns
versions, guardrails, readiness booleans, and required enablement steps, but never returns API keys,
admin tokens, prompts, raw model responses, scraping output, or affiliate payloads. Staging smoke
checks the API endpoint and web proxy before validating recommendation behavior.

## 2026-08-06: Gate 6A Introduces Mock-Only AI Router

Status: Accepted

Model selection before intent parsing is introduced as a mock-only router behind
`FEATURE_AI_ROUTER=false` by default. Allowed modes are `disabled` and `mock`. The mock router never
calls OpenAI, never requires an API key, and only exposes `intent-parser-v0`. When enabled, selecting
the fallback model forces the existing deterministic parser path. Router failures also fall back to
`intent-parser-v0`, so recommendation behavior remains safe if the router misbehaves.

## 2026-08-06: Gate 6B Adds Provider Router With Cache And Cost Logs

Status: Accepted

The AI router gains OpenAI, Anthropic, and Mock providers behind `FEATURE_AI_ROUTER` and
`AI_ROUTER_MODE=disabled|mock|live`. Live calls require env-managed API keys. Redis caches
parsed intents by query hash. Cost/token metrics are logged and exposed on admin metrics endpoints
without automatic budget enforcement. Runtime strategy may switch between `cost_optimized` and
`quality_optimized` via `/admin/router/config` without accepting secrets.

## 2026-08-06: Gate 7 Adds Logging-First Contextual Bandit

Status: Accepted

Provider selection can be optimized by a LinUCB contextual bandit behind
`FEATURE_BANDIT_ROUTER=false` and `BANDIT_ROUTER_MODE=disabled|logging|active`. Logging mode
never changes live routing. Active mode applies only after enough rewarded samples. Decisions
persist to `bandit_logs` for offline training. Reward is a heuristic mix of quality, cost, and
latency with no budget hard-stop. Design details live in `docs/BANDIT_DESIGN.md`.

## 2026-08-06: Gate 8 Adds Anonymous Personalization

Status: Accepted

Personalization is gated by `FEATURE_PERSONALIZATION=false`. Identity uses opaque anonymized
IDs only (no email/phone). Profiles support opt-out. Bandit context may include user embedding
and engagement features; recommendations may apply a category boost. Missing/failed profile
loads always fall back to the non-personalized path.

## 2026-08-06: Gate 9 Adds Chinese Providers And Advanced Policies Safely

Status: Accepted

DeepSeek/Qwen/ERNIE adapters and neural/RLHF/Bayesian tooling are introduced behind explicit
feature flags that default to false. Chinese providers cannot be selected unless
`FEATURE_CHINESE_LLM_PROVIDERS=true` and keys are present. Advanced policies refuse activation
without their flags. Admin model status exposes key booleans only. Benchmarks may run on
synthetic data when logs are empty.

## 2026-09-06: CP4 Adds a Read-Side Product Data Provider Abstraction

Status: Accepted

Product/offer/price lookups go through a new `ProductDataProvider` protocol in `app/providers/`
(`search_products` / `get_product` / `get_offers` / `get_price` / `get_price_history`) plus a
`ProviderRegistry`. This is separate from the affiliate ingestion pipeline: providers are queried
on demand by the URL price-checker and the decision engine and never write to the database. The
first implementation is `KeepaProvider` (Amazon catalogue + multi-year price history, one
marketplace per instance via `KEEPA_DOMAIN`, default `6` = Amazon.ca). It is registered only when
`KEEPA_API_KEY` is set (`sync: false`, never committed); with no key the registry is empty and
lookups return empty. `GET /admin/providers` reports what is wired without exposing secrets. A
Google Shopping vendor for multi-merchant comparison is planned behind the same interface. Details
in `docs/PRODUCT_DATA_PROVIDERS.md`.

## 2026-09-07: CP9–CP11 Add a Deterministic Decision Engine

Status: Accepted

`app/services/decision/` turns a price-history series + a current price into trailing-window
statistics (CP9), an effective price = base + shipping + guaranteed components (CP10), and a
transparent 0–100 score with a BUY / WAIT / FAIR / UNKNOWN verdict and plain-language reasons
(CP11). It is pure and deterministic — rules only, no ML, and **no input for merchant commission
or affiliate payout anywhere in the scoring path** (spec §24). Thin history yields UNKNOWN rather
than a guessed verdict. The engine reads a series it is handed (live `KeepaProvider` result or,
later, persisted rows); it does not fetch or persist. `GET /admin/providers/price-check` runs it
live against a provider as the staging surface until the public checker UI (CP16). Details in
`docs/DECISION_ENGINE.md`.

## 2026-09-07: CP6 Parses Retailer URLs Into a Product Reference

Status: Accepted

`app/services/product_url.py::extract_product_ref` turns a pasted Amazon URL (`/dp/`,
`/gp/product/`, `/gp/aw/d/`, `/-/en/dp/`, `?asin=` / `?pd_rd_i=`) or a bare 10-char ASIN into
`{retailer, market, product_id, keepa_domain}`. TLD picks the market (`.ca` → CA / Keepa domain
6). `amzn.to` / `a.co` short links resolve only when `follow_redirects=True` (one HEAD, no body).
`GET /admin/providers/price-check` accepts `url=` as an alternative to `product_id=`; a non-`.ca`
marketplace is rejected until a provider covers it.

## 2026-09-07: CP15 Adds Price Alerts (One-Shot, Email-Pluggable)

Status: Accepted

`tracked_products` / `price_observations` / `price_alerts` (migration `202609070001`) let a user
watch a product by URL and get one email when the price moves. Alert kinds: `any_drop` (vs. the
baseline at creation, ≥ `ALERT_MIN_DROP_PCT`), `below` (a threshold), `at_or_below_average` (vs.
the 90-day average). Alerts are one-shot — on firing, status → `fired`; no repeat emails. Email
goes through an `EmailSender` protocol (`EMAIL_SENDER=console|null`; real SMTP later). The alert
body carries the `?tag=` affiliate link. `run_alert_cycle` re-checks every tracked product via its
provider, records an observation, and fires due alerts; one bad product is skipped, not fatal.
`POST /admin/alerts`, `GET /admin/alerts`, `POST /admin/alerts/run` (admin); `GET
/alerts/unsubscribe?token=` (public). `python -m app.workers.price_poll` is the cron entrypoint —
blueprint cron wiring is a follow-up. Details in `docs/PRICE_ALERTS.md`.

## 2026-09-07: CP16 (API) Adds Public /check and /alerts

Status: Accepted

The `(url | product_id) -> provider -> decision engine` flow is factored into
`app/services/decision/price_check.py::run_price_check`, and the track+alert flow into
`app/services/tracking/service.py::track_and_alert`, both shared with the admin surfaces so they
cannot drift. `GET /check` and `POST /alerts` are unauthenticated and per-IP rate limited via
`app/services/endpoint_limit.py` (fixed 60s window on the existing Redis / in-memory store), gated
on `RATE_LIMIT_ENABLED` so local/tests are unaffected. New settings `CHECK_RATE_PER_MINUTE` (20),
`ALERT_CREATE_RATE_PER_MINUTE` (10). The `/check` web page is the remaining CP16 piece.

## 2026-09-08: Price Poll Runs From GitHub Actions; SMTP Email Sender Added

Status: Accepted

The daily "re-check every tracked product + fire due alerts" cycle runs from
`.github/workflows/price-poll.yml` (cron `0 13 * * *` + manual dispatch), which POSTs
`/admin/alerts/run` per environment — no paid Render cron service. Configured by repo
Variables `STAGING_API_URL` / `PRODUCTION_API_URL` and Secrets
`STAGING_ADMIN_API_TOKEN` / `PRODUCTION_ADMIN_API_TOKEN`; an unset environment is skipped.
`app/workers/price_poll.py` stays as the entrypoint for a Render `type: cron` alternative.
Email gains a third `EMAIL_SENDER` option, `smtp` (`SmtpEmailSender`, stdlib `smtplib` +
STARTTLS, `SMTP_*` settings); a misconfigured `smtp` falls back to `console` with a warning
so the cron never crashes on it.

## 2026-09-08: CP7 + DataForSEO Add Cross-Merchant Comparison

Status: Accepted

`DataForSEOProvider` (Google Shopping `live/advanced`, query-based) supplies offers from other
retailers; `app/services/decision/matching.py::build_comparison` (CP7) decides which are the same
product — deterministic and conservative: brand must match, price within 0.45x–2.4x of the
reference, accessory/bundle keywords reject, blended confidence ≥ 0.55, one offer per merchant,
"cheaper" only flagged when it beats Amazon by ≥ 2%. `run_price_check` calls the comparison
provider (registered only when `DATAFORSEO_LOGIN`/`PASSWORD` are set) with the Keepa product
title after the verdict is computed; any failure there is swallowed so the verdict always
renders. `/check` gains an optional `comparison` block; the web renders it on the verdict card
and `/check/[asin]`. No merchant preference anywhere — offers are ranked by price only.

## 2026-09-09: Cross-Merchant Comparison Moves to a Task-Backed Cache

Status: Accepted

DataForSEO's Google Shopping product data is **task-based — there is no live endpoint**
(the earlier `DataForSEOProvider` posted to `/v3/merchant/google/products/live/advanced`, which
does not exist; the API answered `Invalid Path.`). A task takes seconds-to-minutes and needs
polling, so it cannot run inside a synchronous price-check.

`app/services/decision/comparison_cache.py` (table `merchant_comparisons`) is the bridge.
`run_price_check` calls `resolve_comparison`: a fresh cached row returns its raw offers straight
away; a cold product posts a `task_post` and returns no comparison for that request; a row whose
task is still pending and at least ~20s old is polled inline (so the *next* check of the same
product — or the hourly `/check/[asin]` revalidation — completes it). `run_alert_cycle` also
sweeps pending rows once a day, and `POST /admin/providers/comparison-poll` does it on demand.
Ready rows live 24h; CP7 matching (`build_comparison`) re-runs on every read so the "cheaper?"
call stays correct as the Amazon price moves. Every failure is swallowed — verdict + sparkline
never depend on DataForSEO. Keyword sent to DataForSEO is the Keepa title trimmed to its head
(`shopping_keyword`) because raw Amazon titles are too noisy for Google Shopping. Cost is one
`task_post` per distinct product per 24h, not one per check.

## 2026-09-09: Comparison Polish — URLs, Amazon Echo Filter, Cheaper Gate

Status: Accepted

After the first real DataForSEO results on staging: (1) DataForSEO deprecated the `url` field for
Google Shopping (always `null`) — `_parse_items` now falls back to `shopping_url` (the Google
Shopping product page). (2) `build_comparison` skipped only the literal `"Amazon.ca"` merchant;
`_is_reference_echo` now drops any same-family name ("Amazon", "Amazon.com", "Amazon Warehouse")
so a third-party marketplace listing of the reference product no longer appears as a rival. (3)
"Cheaper at X" is a strong claim — it is now flagged only when the cheapest offer's blended match
confidence is ≥ 0.65 (`_CHEAPEST_MIN_CONFIDENCE`), not merely ≥ 0.55 (the inclusion bar); a
weaker match still shows in the list, just not highlighted.

## 2026-09-09: Comparison Shows Only Cheaper Offers

Status: Accepted

The comparison block answers one question — "can I pay less elsewhere?" — so `build_comparison`
now drops any candidate priced above the reference (`_DISPLAY_MAX_RATIO = 1.0`) before scoring.
This also removes the noise the first real results surfaced: a foreign reseller ("delldxb.com")
priced at 1.7x the Amazon price was passing the wide match band. Same-price and cheaper offers
still show; "Amazon.ca has the best price" is the fallback when nothing survives.

## 2026-09-09: Acquisition Advisor (Layer 2) — Price Checker → Shopping Advisor

Status: Accepted

Confirmed core identity: SaveIQ is a **shopping advisor**, not a price checker. The price
engine (`app/services/decision/`) is Layer 1 — "is this price good vs its history". The new
`app/services/acquisition/` is Layer 2 — "which way of getting this product is best for me":
buy outright, 0% financing, bring-it-back lease, device+plan bundle, or refurb/last-gen.
`compute_tco` places every cash flow on a month index and discounts to present value when the
buyer sets an `annual_discount_rate` (so "keep the cash, pay monthly" is scored fairly),
credits resale value still held at the horizon, and models a lease as a return-vs-keep based on
the buyer's upgrade cadence. `compare_paths` ranks by discounted TCO and emits transparent
`caveats` (owns-nothing, lease-is-a-trap for long holders, lock-in, service-sensitivity,
business support lever) plus a fixed `verify_first` list of what SaveIQ structurally cannot
know. Deterministic and payout-free, exactly like the price verdict; the LLM layer (Layer 3,
not built) will select options for a natural-language query and narrate — it does not do the
arithmetic. Admin surface: `GET /admin/acquisition/catalog` + `/admin/acquisition/compare`.
The catalogue (`acquisition_catalog.json`) currently holds one illustrative worked example
(iPhone 17 Pro, 4 options, all `verify:true`); real product + carrier-plan data is the next
data task.

## 2026-09-09: Acquisition Advisor Composes Options From Category/Channel Rulesets

Status: Accepted (supersedes the per-product catalogue from the same day)

The first cut stored acquisition options per product, which does not scale — millions of SKUs,
only a handful of ways to pay for one. Replaced the per-product `acquisition_catalog.json` with
small category/channel data: `programs.json` (~7 acquisition-program rulesets — retail, carrier
financing, bring-it-back, retailer 0% financing, Apple/Amazon refurb), `carrier_plans.json`
(~4 Canadian plan price points), `depreciation.json` (resale-value curves by category+age),
`demo_products.json` (a few reference products for the `?slug=` path). `composer.compose_options`
turns a `ProductContext` (retail price + category + brand + tier) into concrete
`AcquisitionOption` rows by matching applicable programs: category/brand/price-floor gates, a
carrier-eligibility check (phones/cellular only), and a plan-cost line that attaches only to
carrier-eligible devices. A product matching no special program still gets "buy outright". Data
is best-effort estimates from public reporting (Sept 2026), every option `verify:true` — keeping
it current is a ~20-row recurring data task, not code. Admin: `GET /admin/acquisition/data` +
`/compare` (by demo slug or explicit price+category).

## 2026-09-09: Price Check Surfaces the Amazon Buy-Box Spread

Status: Accepted

The price verdict only looks at the buy box, but one ASIN has many Amazon sellers at different
prices. `app/services/decision/offer_spread.py::summarize_amazon_offers` turns the live Keepa
offer list into an `AmazonOfferSpread` — the cheapest alternate *new* listing (only when it
undercuts the buy box), the cheapest *used / renewed*, counts, an FBA flag, and the saving vs
the buy box. `run_price_check` calls `get_offers` best-effort after the verdict (guarded by the
`get_offers` capability, all failures swallowed) and adds `spread` to `PriceCheckResult`; `/check`
and the admin price-check gain a `spread` block; the web renders `<OfferSpread>` on the verdict
card and `/check/[asin]`. To keep the extra offer fetch from tripling Keepa `/product` calls,
`KeepaProvider._fetch_product` gained a 60-second per-ASIN cache of the richest payload seen, so
one price-check's 3–4 provider calls collapse toward one Keepa hit.

## 2026-09-09: Public /acquire Endpoint Wires the Product Page to Layer 2

Status: Accepted

`GET /acquire?product_id=<asin>` (public, per-IP rate limited via `ACQUIRE_RATE_PER_MINUTE`,
default 20) resolves an ASIN through Keepa to price + category + brand,
`product_map.infer_product_context` maps the Amazon category text onto the acquisition taxonomy
(keyword rules; anything unrecognised → `general`, which only the "*" programs cover so the
advisor still answers), `compose_options` + `compare_paths` produce the ranked recommendation
for the buyer profile from the query. The web renders `<AcquireBlock>` on the verdict card and
`/check/[asin]` (fetched in parallel with the price check, non-blocking on the homepage). This
is the "price checker → shopping advisor" wiring — the check page now shows verdict + sparkline
+ Amazon spread + cross-merchant comparison + acquisition paths, all three engine layers.
