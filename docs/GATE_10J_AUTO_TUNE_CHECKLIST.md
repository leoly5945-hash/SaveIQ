# Gate 10J: Auto-Tune Enablement Checklist

Generated: 2026-08-13  
Updated: 2026-08-25  
Status: **STAGING DRY-RUN EXERCISED, PASS** (PR #37/#38) — production `FEATURE_AUTO_TUNING` stays **false** until a separate, explicit sign-off.

## Scope

Enable `FEATURE_AUTO_TUNING` (prefer dry-run first) for capped hparam adjustments. Must **never** flip:

- `FEATURE_NEURAL_BANDIT`
- `FEATURE_RLHF_ROUTER`
- `BANDIT_POLICY`

These remain human-only forever (`HUMAN_ONLY_FLAGS` in `apps/api/app/services/safety/service.py`). Auto-tune may only propose/apply epsilon, α/β/γ, and cache TTL within `AUTO_TUNE_*` caps.

## Preconditions

- [x] Gate 10I **code complete** and **armed in production** (PR #35 + pin PR #36; `/admin/kill-switch/*` live; `armed=true`, `tripped=false`)
- [ ] Gate 10I **prod-drill** (still deferred — zeros canary + parser fallback on live traffic)
- [x] Auto-tune still **OFF** in production Blueprint (`FEATURE_AUTO_TUNING=false`)
- [x] Cap bounds recorded from `apps/api/app/core/settings.py` defaults (operator should re-read before any prod window):
  - `AUTO_TUNE_DRY_RUN=true`
  - `AUTO_TUNE_CANARY_ENABLED=false` (do not enable canary ramp in this gate)
  - `AUTO_TUNE_INTERVAL_SECONDS=300`, `AUTO_TUNE_MIN_SAMPLES=100`
  - epsilon `[0.01, 0.4]`, cache TTL `[60, 900]`
  - canary step caps exist in code (`max 25%`, `step 5%`) but stay unused while canary auto-ramp is off
- [ ] Prefer `AUTO_TUNE_DRY_RUN=true` for first **production** window (not started)

## Staging scaffold (this pass)

Script: `scripts/gate10j_auto_tune.py` · Make: `make gate10j-auto-tune ARGS='…'`  
Writes **only** `render.yaml`. Refuses any `*production*` Blueprint path. urllib + `X-Admin-Token`. Dry-run / no write unless `--confirm-autotune`.

```bash
export STAGING_ADMIN_TOKEN=...
export PROD_ADMIN_TOKEN=...

make gate10j-auto-tune ARGS='--stage check'
make gate10j-auto-tune ARGS='--stage staging-dry-run'   # prints diff; does not write
make gate10j-auto-tune ARGS='--stage staging-dry-run --confirm-autotune'
# → Render Manual Sync Blueprint saveiq (staging) — NOT saveiq-production
make gate10j-auto-tune ARGS='--stage evaluate'
make gate10j-auto-tune ARGS='--stage cleanup --confirm-autotune'
```

- [x] Staging dry-run scaffolding exists (`check` / `staging-dry-run` / `evaluate` / `cleanup`)
- [x] Operator ran `staging-dry-run --confirm-autotune` (`render.yaml` `FEATURE_AUTO_TUNING=true`, merged **PR #37**)
- [x] Staging `evaluate` observed **propose-only**, 2026-08-25 — armed via runtime overlay (`--confirm-autotune`) since Blueprint Sync had not yet propagated:
  `applied=false`, `dry_run=true`, proposal `cache_ttl_seconds 300->270` (`reason=latency_headroom`), hparams unchanged before/after, `audit_proposed=1`, `audit_applied=0`
- [x] Staging cleanup: runtime overlay disarmed + `render.yaml` `FEATURE_AUTO_TUNING` reverted to `false` (merged **PR #38**)
- [ ] Operator has clicked **Render Manual Sync** on staging (`saveiq`) after PR #38, so `false` is durable on the live service (script writes/overlay only — Sync is a manual dashboard step)

`evaluate` without Sync can arm a **runtime overlay** (`POST /admin/safety/config` with `dry_run=true`) only when `--confirm-autotune` is passed. Env flag still needs Blueprint Sync to be durable. Overlay is not production. This is exactly the path used above — the first `evaluate` (no `--confirm-autotune`) correctly reported `auto_tune_disabled` / `skipped=true` because the PR #37 Sync had not landed yet; the second `evaluate --confirm-autotune` armed the overlay directly and produced the propose-only result above.

## Enablement (production — all unchecked)

1. Staging: auto-tune dry-run → observe propose events — **DONE** 2026-08-25 (PR #37/#38, propose-only PASS; final Manual Sync of the `false` revert still pending)
2. Production Blueprint: enable with dry-run → Sync → monitor
3. Only then consider `AUTO_TUNE_DRY_RUN=false` with **explicit** sign-off
4. Confirm human-only flags remain untouched after soak

Do **not** add `--allow-auto-tuning` to production Blueprint validation until that sign-off. `render-production.yaml` must keep `FEATURE_AUTO_TUNING=false`.

## Out of scope

- Production `FEATURE_AUTO_TUNING=true`
- `AUTO_TUNE_DRY_RUN=false` on any environment in this pass
- Flipping neural / RLHF / `BANDIT_POLICY` / Chinese LLM
- Affiliate modules (`src/affiliate`, `src/router`, `apps/api/app/integrations/`)

## References

- `lamviec.md` — operator handover
- `docs/GATE_10I_KILL_SWITCH_CHECKLIST.md`
- `docs/GATE_10E_CLOSEOUT.md`
- `docs/RUNBOOK.md` §3d
- `apps/api/app/services/safety/service.py` (`HUMAN_ONLY_FLAGS`, `_auto_tune`)
- Admin: `POST /admin/safety/evaluate`, `GET /admin/safety/audit`, `POST /admin/safety/config`
