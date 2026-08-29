# Affiliate click attribution & reconciliation

Publisher-side foundation so **every outbound click is logged server-side** with
a SubID we can match against network conversion reports — the evidence needed to
audit payouts and dispute under-reporting.

## Click flow

```
visitor clicks "View deal"
  → GET  saveiq.ca/go/<offer_id>?t=<product|affiliate>&aid=<anon_id>   (web route handler)
      → GET  <api>/go/<offer_id>?...            (server-to-server; forwards UA / referer / XFF / prefetch headers)
          • resolves the offer's product/affiliate URL
          • generates click_id = uuid4().hex   (also the SubID)
          • bot check (UA denylist + Sec-Purpose/Purpose: prefetch) → is_bot flag
          • dedup: same offer + same visitor (anon id, else salted IP hash) within
            AFFILIATE_REDIRECT_DEDUP_SECONDS reuses the prior click_id
          • append-only INSERT into affiliate_click_events
            (click_id, subid, network, landing_url, ip_hash, is_bot, …)
          • 302 → <affiliate_url>?<network_param>=<click_id>
      ← 302 Location
  ← 302 Location (Cache-Control: no-store, X-Robots-Tag: noindex)
```

If the offer has no destination or the API is unreachable, the web handler 302s
the visitor to the homepage rather than a dead end.

`network` comes from `NETWORK_BY_PROVIDER` (the ingestion `provider_source`), and
the SubID param name from `SUBID_PARAM` (`impact`→`subId1`, `rakuten`→`u1`,
`cj`→`sid`, `awin`→`clickref`, `amazon`→`ascsubtag`, …) — see
`app/services/affiliate/attribution.py`.

## Conversion ingest

`POST /affiliate/postback/<network>?secret=<AFFILIATE_POSTBACK_SECRET>`

Accepts a JSON body or form-encoded payload (falls back to the query string).
Auth is the shared `AFFILIATE_POSTBACK_SECRET`; returns 503 until it is set.
The raw payload is stored verbatim in `affiliate_conversions.raw_payload` as
dispute evidence. SubID / order value / commission / status are pulled from a
tolerant field map and normalised (`status` → pending / approved / reversed;
amounts → cents). If the payload carries a stable `external_id`, re-posts update
the row in place (idempotent).

Matching: the SubID is looked up against `affiliate_click_events.click_id`; on a
hit the conversion is linked to that click (`click_event_id`).

Per-network importers that pull each network's reporting **API** on a schedule
(needs credentials that only exist after a program is approved) plug into
`record_conversion()` the same way.

## Reconciliation

`GET /admin/affiliate/reconciliation?days=30` (admin token) groups clicks vs
reported conversions per `(network, merchant)`:

| field | meaning |
| --- | --- |
| `clicks` / `bot_clicks` / `billable_clicks` | logged clicks; bots excluded from billable |
| `conversions` / `conversions_reversed` | non-reversed vs reversed conversions in the window |
| `unmatched_conversions` | reported but no matching click (SubID lost / stripped) |
| `conversion_rate`, `epc_cents` | over billable clicks |
| `discrepancy` | `no_conversions_despite_clicks` when ≥25 billable clicks and 0 conversions — worth raising with the network |

The click log is the supporting evidence for any dispute. It proves qualified
traffic + the SubID we sent; it does **not** prove a sale — the network's report
is still the source of truth for payment.

## Config

| env | default | notes |
| --- | --- | --- |
| `AFFILIATE_POSTBACK_SECRET` | _unset_ | shared secret for `/affiliate/postback/*`; also salts `ip_hash`. Set per-service in Render. |
| `AFFILIATE_REDIRECT_DEDUP_SECONDS` | `10` | repeat-click SubID reuse window |

## Not covered (network-side / ITP)

Long-window and cross-device attribution still depend on the network + advertiser
(S2S postback, first-party tracking domains, conversion APIs). Prefer networks
with server-side tracking; treat Amazon (24h cookie, no S2S) as best-effort.
Cross-device is unrecoverable without accounts, which the site does not have.
