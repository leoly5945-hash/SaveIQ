# Cursor prompt: fix the 26 failing `api` tests (stale mock fixture dates)

## Context

`apps/api`'s CI `api` job has failed on the same 26 tests all session
(`tests/test_admin_affiliate_api.py`, `test_affiliate_ingestion.py`,
`test_recommendation_eval_fixtures.py`, `test_recommendations_api.py`,
`test_search_api.py`). Confirmed root cause by running
`tests/test_affiliate_ingestion.py::test_successful_sync_ingests_mock_data`
locally:

```
SyncStats(received=12, inserted=0, updated=0, skipped=12, rejected=0,
duplicate=1, stale=11, errors=0)
```

`app/services/affiliate/mock_provider.py` hardcodes fixture
`source_timestamp` values as absolute strings, mostly `"2026-07-09T..."`
(one deliberately old one at `"2026-05-01T..."` meant to exercise a
different code path). `app/services/affiliate/ingestion.py`'s `_is_stale()`
rejects anything older than `datetime.now(UTC) - timedelta(days=30)`. As
real/simulated "now" has advanced past `2026-08-08` (30 days after the
fixture date), the fixtures aged past the staleness window and now get
silently marked `stale` instead of `inserted` — so the mock feed the tests
sync now inserts **zero** offers, and every test that depends on search
results / recommendations existing fails downstream (empty result lists,
`IndexError` on `results[0]`, evaluation fixtures expecting `>= 1`
recommendation, etc.). This is a test-data-rot bug, not a logic bug in
search/recommendations/ingestion themselves.

## Task

Fix it durably — not by bumping the 30-day threshold (that just delays the
same rot) and not by hardcoding a later date (same problem, later).
Preferred approach: make `mock_provider.py`'s fixture timestamps relative
to call time instead of fixed calendar dates, e.g. replace
`dt("2026-07-09T10:00:00")`-style absolute strings with something like
`datetime.now(UTC) - timedelta(days=N, hours=H)` per fixture, preserving
each fixture's *relative* age/ordering (the deliberately-stale one should
stay clearly older than 30 days; the rest should stay clearly fresher).
Keep relative offsets between fixtures intact — some tests likely depend on
relative ordering/recency, not just absolute freshness.

If a relative-time approach turns out to conflict with something else
fixture-related (e.g. coupon `starts_at`/`expires_at` windows also
hardcoded to 2026 dates in the same file), fix those the same way rather
than leaving a second latent rot bug.

Do not touch `_is_stale()`'s 30-day threshold or any non-test/non-fixture
production code — the bug is entirely in fixture data being time-relative
data expressed as absolute dates.

## Verify

Run from `apps/api`:

```bash
../../.venv/bin/python -m pytest tests/test_admin_affiliate_api.py \
  tests/test_affiliate_ingestion.py \
  tests/test_recommendation_eval_fixtures.py \
  tests/test_recommendations_api.py \
  tests/test_search_api.py -v
```

All should pass. Then run the full suite (`pytest`) to confirm nothing
else regressed, plus `ruff check app tests` and `mypy app` per repo
convention.

## Explicitly out of scope

- Anything under `Gate 10I`/`Gate 10J` (kill switch, auto-tune).
- The uncommitted `src/affiliate`, `src/router`,
  `apps/api/app/integrations` workstream.
- `apps/web` — unrelated to this bug.
- Any production data/Blueprint change.

## Report back

Which tests were fixed and how, full `pytest` result, and confirm
`ruff`/`mypy` are clean.
