# Gate 3 Closeout

Gate 3 validates the staging search slice end to end with deterministic mock affiliate data only.
No web scraping, real affiliate integration, production checkout, or full AI agent behavior is
enabled.

## Scope Closed

- Cost-optimized Render staging Blueprint with API, web, PostgreSQL, and Key Value resources.
- Deterministic mock affiliate sync and normalized stored search data.
- Public search flow through API and web proxy.
- Offer result explainability using stored match and ranking reasons.
- Staging-only click tracking for mock product and affiliate URL taps.
- Admin-only staging summary, seed controls, and click analytics.
- Live smoke command covering API, web, admin, search, click, analytics, and proxy paths.

## Staging URLs

| Surface    | URL                                                      |
| ---------- | -------------------------------------------------------- |
| Web        | `https://dealhunter-staging-web.onrender.com`            |
| API        | `https://dealhunter-staging-api.onrender.com`            |
| API health | `https://dealhunter-staging-api.onrender.com/health`     |
| Web health | `https://dealhunter-staging-web.onrender.com/api/health` |

## Validation Evidence

Last verified: 2026-07-24

```text
staging_smoke=ok
api_health=ok
web_health=ok
mock_sync=completed
admin_summary=offers=6
api_search=count=2
web_search_proxy=count=2
click_tracking=offer_id=1
web_click_proxy=offer_id=1
click_analytics=total=6
web_admin_summary_proxy=offers=6
web_click_analytics_proxy=total=6
```

Run the same check after future staging deploys:

```bash
ADMIN_API_TOKEN=<render-admin-token> PYTHON=.venv/bin/python make staging-smoke
```

The token must be the `ADMIN_API_TOKEN` value configured on the Render
`dealhunter-staging-api` service. Do not commit or paste the secret value.

## Known Deferrals

- Background worker and scheduler remain deferred to control staging cost.
- Render free PostgreSQL is temporary and can expire after 30 days.
- Key Value is staging-only and not treated as durable production storage.
- Real affiliate connectors are not implemented.
- AI recommendation orchestration is not implemented.
- Web scraping remains explicitly out of scope.

## Exit Criteria

| Criterion                                              | Status |
| ------------------------------------------------------ | ------ |
| Staging Blueprint applied from `render.yaml`           | PASS   |
| API health check passes                                | PASS   |
| Web health check passes                                | PASS   |
| Mock provider sync succeeds                            | PASS   |
| Search returns normalized mock offers                  | PASS   |
| Web search proxy returns API-backed offers             | PASS   |
| Click tracking records mock product and affiliate taps | PASS   |
| Admin analytics reports tracked clicks                 | PASS   |
| Staging remains mock-only                              | PASS   |

Gate 3 is closed.
