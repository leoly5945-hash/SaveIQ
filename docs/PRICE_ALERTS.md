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
| `POST /admin/alerts` | admin | create a tracked product + alert from `{email, url \| product_id, kind, threshold_cents?}`; does one initial observation |
| `GET /admin/alerts` | admin | list alerts (latest 200) |
| `POST /admin/alerts/run` | admin | run one `run_alert_cycle`, returns `CycleStats` |
| `GET /alerts/unsubscribe?token=` | **public** | deactivate an alert; same response whether the token matched |

Public alert creation + rate limiting + the `/check` UI is CP16.

## Scheduled run

`python -m app.workers.price_poll` runs one cycle. Not wired to a Render service
yet — the blueprint needs a `type: cron` entry (daily). Until then, hit
`POST /admin/alerts/run` (or run the module) manually.

## Config

| env | default | meaning |
| --- | --- | --- |
| `EMAIL_SENDER` | `console` | `console` \| `null` |
| `ALERT_FROM_EMAIL` | `alerts@saveiq.ca` | From: header |
| `PUBLIC_SITE_URL` | `https://www.saveiq.ca` | base for the unsubscribe link |
| `ALERT_MIN_DROP_PCT` | `1.0` | min % drop for an `any_drop` alert to fire |
