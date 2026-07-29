# Gate 4 Closeout

Gate 4 validates the mock recommendation quality loop end to end on staging. It remains
deterministic and staging-only: no web scraping, real affiliate integration, production checkout,
LLM intent parser, or complete AI agent behavior is enabled.

## Scope Closed

- Deterministic rule-based recommendation endpoint backed by normalized mock offers.
- Offline recommendation fixture evaluation and local/CI evaluator.
- Persisted recommendation traces for staging audit.
- Admin trace viewer, trace drilldown, and trace comparison UI.
- Deterministic decision explanations for recommended offers.
- Staging Helpful/Not helpful feedback capture and feedback summary.
- Staging retention preview/prune controls for recommendation traces and feedback.
- Recommendation quality cockpit with readiness scoreboard and closeout checklist.
- Quality report export that snapshots evaluation, feedback, traces, staging counts, retention
  preview, and version metadata.
- Explicit recommendation strategy, rule, parser, ranker, and fixture versions in responses,
  persisted traces, evaluation summaries, quality exports, staging UI, and smoke checks.

## Staging URLs

| Surface    | URL                                                      |
| ---------- | -------------------------------------------------------- |
| Web        | `https://dealhunter-staging-web.onrender.com`            |
| API        | `https://dealhunter-staging-api.onrender.com`            |
| API health | `https://dealhunter-staging-api.onrender.com/health`     |
| Web health | `https://dealhunter-staging-web.onrender.com/api/health` |

## Validation Evidence

Last verified: 2026-07-29

```text
staging_smoke=ok
api_health=ok
web_health=ok
mock_sync=completed
admin_summary=offers=6
api_search=count=2
web_search_proxy=count=2
api_recommendations=count=1 trace=23
recommendation_explanation=signals=4
recommendation_versions=rule=ruleset-2026-07-27-gate-4o parser=intent-parser-v0 ranker=ranker-v0
web_recommendation_proxy=count=1 trace=24
web_recommendation_explanation_proxy=signals=4
web_recommendation_versions_proxy=rule=ruleset-2026-07-27-gate-4o
recommendation_feedback=offer_id=1
web_recommendation_feedback_proxy=offer_id=1
click_tracking=offer_id=1
web_click_proxy=offer_id=1
click_analytics=total=32
web_admin_summary_proxy=offers=6
recommendation_traces=total=24 row_rule=ruleset-2026-07-27-gate-4o
web_recommendation_trace_proxy=total=24 row_rule=ruleset-2026-07-27-gate-4o
recommendation_evaluation=passed=4 failed=0 rule=ruleset-2026-07-27-gate-4o fixtures=fixtures-v0
web_recommendation_evaluation_proxy=passed=4
recommendation_feedback_summary=helpful=8 not_helpful=8 helpful_rate=0.50 coverage=0.67
web_recommendation_feedback_summary_proxy=total=16 coverage=0.67
recommendation_retention_preview=delete_traces=14 retain=10
web_recommendation_retention_preview_proxy=delete_traces=14
recommendation_quality_export=traces=24 feedback=16 rule=ruleset-2026-07-27-gate-4o
web_recommendation_quality_export_proxy=version=gate-4p-quality-export-v1 rule=ruleset-2026-07-27-gate-4o
web_click_analytics_proxy=total=32
```

Run the same check after future staging deploys:

```bash
ADMIN_API_TOKEN=<render-admin-token> PYTHON=.venv/bin/python make staging-smoke
```

The token must be the `ADMIN_API_TOKEN` value configured on the Render
`dealhunter-staging-api` service. Do not commit or paste the secret value.

## Known Deferrals

- The recommendation system is still deterministic and rule-based.
- LLM intent parsing is deferred until evaluation criteria and prompt contracts are finalized.
- Real affiliate connectors are not implemented.
- Web scraping remains explicitly out of scope.
- Background worker and scheduler remain deferred to control staging cost.
- Render free PostgreSQL is temporary and can expire after 30 days.
- Recommendation traces and feedback are staging quality signals, not production user analytics.

## Exit Criteria

| Criterion                                                 | Status |
| --------------------------------------------------------- | ------ |
| Recommendation endpoint returns stored-offer results      | PASS   |
| Web recommendation proxy returns API-backed results       | PASS   |
| Decision explanations are deterministic and present       | PASS   |
| Recommendation traces persist row-level version metadata  | PASS   |
| Admin trace viewer, drilldown, and comparison are present | PASS   |
| Fixture evaluation passes all deterministic cases         | PASS   |
| Feedback summary reports Helpful/Not helpful coverage     | PASS   |
| Retention preview runs in dry-run mode                    | PASS   |
| Quality export includes traces, feedback, and versions    | PASS   |
| Staging remains mock-only                                 | PASS   |

Gate 4 is closed.
