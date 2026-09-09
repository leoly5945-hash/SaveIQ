# Price Alerts (CP15)

Users watch a product — usually by pasting an Amazon.ca URL — and get one email
when the price moves the way they asked. This is the retention loop: the alert
email carries the affiliate link back to the product.

## Data model (`app/models/tracking.py`, migration `202609070001`)

| table | holds |
| --- | --- |
| `tracked_products` | one row per `(provider, provider_product_id, market)` a user asked us to watch |
| `price_observations` | append-only price checks for a tracked product; dedupe on `(tracked_product_id, observed_at)`. Carries the effective price, the 90-day average, and a snapshot of the verdict/score at capture. |
| `price_alerts` | an email + a trigger on a tracked product. `unsubscribe_token` (32-byte urlsafe) gates the public unsubscribe link. |

Separate from the affiliate `price_history` chain (that one is keyed to
`merchant_listings` from the ingestion pipeline).

## Alert kinds (`AlertKind`)

| kind | fires when |
| --- | --- |
| `any_drop` | effective price is ≥ `ALERT_MIN_DROP_PCT` (default 1 %) below the **baseline** — the price when the alert was created |
| `below` | effective price ≤ `threshold_cents` (required) |
| `at_or_below_average` | effective price ≤ the observation's 90-day average |

Alerts are **one-shot**: on firing, `status` → `fired` and the email tells the
user to set a new one. No repeat emails, no spam risk.

## Service (`app/services/tracking/service.py`)

* `get_or_create_tracked_product(...)`, `record_observation(...)` (dedupes),
  `latest_observation(...)`
* `create_alert(db, tracked, *, email, kind, threshold_cents=None)` — normalises
  the email, sets the baseline from the latest observation, mints the token
* `evaluate_alert(alert, observation, *, min_drop_pct)` — **pure**, deterministic
  trigger check → `AlertTrigger | None`
* `unsubscribe(db, token)` — idempotent
* `run_alert_cycle(db, registry, *, email_sender, settings=None, now=None)` — for
  every tracked product: fetch the current price + history via its provider, run
  the decision engine, record an observation, then fire + email any due alerts.
  One bad product logs and is skipped; it never stops the cycle.

## Email (`app/services/tracking/email.py`)

`EmailSender` protocol. `EMAIL_SENDER=console` (default) logs the message;
`null` drops it. A real SMTP / API sender slots in here later without touching
callers. The alert body links to
`https://www.amazon.ca/dp/<ASIN>?tag=<AMAZON_ASSOCIATE_TAG>` and an unsubscribe
URL under `PUBLIC_SITE_URL`.

## Endpoints

| endpoint | auth | purpose |
| --- | --- | --- |
| `POST /alerts` | **public** (CP16) | create from `{email, url \| product_id, kind, threshold_cents?}`; per-IP rate limited (`ALERT_CREATE_RATE_PER_MINUTE`, only when `RATE_LIMIT_ENABLED`) |
| `POST /admin/alerts` | admin | same, no rate limit |
| `GET /admin/alerts` | admin | list alerts (latest 200) |
| `POST /admin/alerts/run` | admin | run one `run_alert_cycle`, returns `CycleStats` |
| `GET /alerts/unsubscribe?token=` | **public** | deactivate an alert; same response whether the token matched |

Both create paths go through `track_and_alert()`. The `/check` web UI is the
remaining CP16 piece.

## Scheduled run

`.github/workflows/price-poll.yml` runs daily at 13:00 UTC (and on manual
dispatch): it `POST`s `/admin/alerts/run` for each configured environment. No
extra Render service, no cost. Configure per env (any unset one is skipped):

* Repo **Variables**: `STAGING_API_URL`, `PRODUCTION_API_URL`
* Repo **Secrets**: `STAGING_ADMIN_API_TOKEN`, `PRODUCTION_ADMIN_API_TOKEN`

`python -m app.workers.price_poll` remains the entrypoint for a paid Render
`type: cron` if you ever prefer that.

## Config

| env | default | meaning |
| --- | --- | --- |
| `EMAIL_SENDER` | `console` | `console` (log) \| `null` (drop) \| `smtp` (send) |
| `ALERT_FROM_EMAIL` | `alerts@saveiq.ca` | From: header |
| `PUBLIC_SITE_URL` | `https://www.saveiq.ca` | base for the unsubscribe link |
| `ALERT_MIN_DROP_PCT` | `1.0` | min % drop for an `any_drop` alert to fire |
| `SMTP_HOST` | *(unset)* | required for `EMAIL_SENDER=smtp`; unset ⇒ falls back to `console` |
| `SMTP_PORT` | `587` | |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | *(unset)* | omitted ⇒ no AUTH (relay) |
| `SMTP_USE_TLS` | `true` | STARTTLS after connect |
