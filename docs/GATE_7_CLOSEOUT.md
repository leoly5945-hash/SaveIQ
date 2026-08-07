# Gate 7 Closeout — Contextual Bandit Router Optimization

Date: 2026-08-06  
Branch: `feature/gate-7-bandit-router`

## Summary

Gate 7 adds a **LinUCB contextual bandit** that can learn provider selection from logged
context → action → reward tuples. Defaults remain safe:

| Flag | Default |
|---|---|
| `FEATURE_BANDIT_ROUTER` | `false` |
| `BANDIT_ROUTER_MODE` | `disabled` |

Recommended first enablement: `FEATURE_BANDIT_ROUTER=true` + `BANDIT_ROUTER_MODE=logging`
(collects data, never overrides rule-based routing).

## Delivered

1. **Features** — fixed vector (`bias`, query length/words, complexity one-hots, intent/market,
   hour sin/cos, user-id flag). See `docs/BANDIT_DESIGN.md`.
2. **LinUCB agent** — pure Python (no numpy/sklearn dependency) with epsilon-greedy explore.
3. **Reward** — `α·quality + β·(1−cost) + γ·(1−latency)` heuristic (weights configurable).
4. **Persistence** — `bandit_logs` table + Alembic migration `202608060001`.
5. **Router integration** — logging mode never changes behavior; active mode only applies when
   the agent is ready (`BANDIT_MIN_SAMPLES_READY`), else falls back to rule-based.
6. **Admin** — `/admin/bandit/status|metrics`, `POST /admin/bandit/train|reset`.
7. **Public** — `GET /bandit/status` + web proxy `GET /api/bandit/status`.
8. **Offline eval** — `train` endpoint runs a progressive offline replay and stores summary metrics.
9. **Smoke** — bandit/router checks soft-skip on HTTP 404 until staging is redeployed.

## Safety

- Feature default off; logging-first.
- No API keys in bandit responses.
- DB log write failures do not break recommendations.
- Active mode still falls back when cold-start / unready.

## Verification (local)

```bash
.venv/bin/ruff check apps/api/app apps/api/tests scripts
.venv/bin/mypy apps/api/app
.venv/bin/pytest apps/api/tests -q
```

Staging smoke still requires Gate 6/7 image deploy for bandit endpoints to leave
`skipped=not_deployed`.

## Follow-ups (math collaboration)

- Feature selection / normalization refinement
- Reward weight tuning (α, β, γ) and CTR-backed quality
- Richer offline metrics (IPS, DR, cumulative regret curves)
- A/B test active bandit vs rule-based after logging corpus is large enough
