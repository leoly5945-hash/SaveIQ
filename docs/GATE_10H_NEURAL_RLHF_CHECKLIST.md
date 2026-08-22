# Gate 10H: Neural / RLHF Evaluation Checklist

Generated: 2026-08-10  
Updated: 2026-08-22 (n100 soak PASS; prod RLHF Blueprint `FEATURE_RLHF_ROUTER=true`)  
Status: IN PROGRESS — prod neural n100 **PASS**; RLHF Blueprint applied (PR / Render Sync next)

This gate is **human-only**. Auto-tune (Gate 10E/10J) must never flip neural/RLHF or `BANDIT_POLICY`.

## Current production baseline (rechecked 2026-08-11)

| Flag / signal | Value |
| --- | --- |
| `FEATURE_AI_ROUTER` / mode | `active=True`, **`live`** |
| Chinese LLM | **ON** (`chinese=True`; DeepSeek configured) |
| `BANDIT_POLICY` / public bandit | runtime **neural** (Blueprint still `linucb`); `feature_bandit_router` logging (`feature_enabled=false`) |
| `FEATURE_NEURAL_BANDIT` | **`true`** (PR #33; Sync verified) |
| `FEATURE_RLHF_ROUTER` | **`true`** in Blueprint (awaiting PR + Render Sync; runtime still `false` until Sync) |
| Kill / autotune | **OFF**, not tripped |
| Canary | enabled **100%** |
| Smoke | `production_smoke=ok` (live + chinese allow flags) |

## Prerequisites

- [x] Gate 10E complete (C4 soak ≥24h, mock_router=ok) — see `docs/GATE_10E_ROLLOUT_REPORT.md`
- [x] Gate 10F complete (`FEATURE_AI_ROUTER=true`, mode=mock) — superseded by 10G
- [x] Gate 10G complete (`mode=live`, Chinese LLM ON, DeepSeek key present)
- [x] Live providers stable for ≥ **24h** after Gate 10G Sync (recheck 2026-08-11: smoke ok, live+chinese, no kill trip)
- [x] Provider/router error rate within Gate 10 plan budgets — **PASS** 2026-08-13 (`http_5xx_rate=0`; LLM series sparse **3&lt;20**, operator `--allow-sparse-llm`; see `artifacts/gate10h_prod_prereq_report.json`)
- [x] Latency within baseline + **10%** — **PASS** 2026-08-13 (`/search` p95=250ms; `/recommendations` p95=2500ms ≤ ×1.1; baseline `artifacts/gate10h_prod_baseline.json`)
- [x] Kill switch / auto-tune still **OFF** (unchanged) — confirmed `/admin/safety/status`
- [x] Staging Neural drill: `gate10h_staging_neural.py` evaluate **PASS** (2026-08-13; neural reward &gt; linucb; cleanup → flag `false`)
- [x] Staging RLHF drill: `gate10h_staging_rlhf_drill.py` evaluate **PASS** (2026-08-13; rlhf reward &gt; linucb; cleanup → flag `false`)

## Production neural soak

Monitor: `scripts/gate10h_monitor_soak.py`. Advance: `scripts/gate10h_advance_neural.py` (requires ≥24h **and** monitor report PASS).

- [x] Soak n10 completed: 2026-08-14 (monitor PASS; advanced to n25 2026-08-17)
- [x] Soak n25 completed: 2026-08-19 (monitor PASS; advanced to n50 2026-08-19)
- [x] Soak n50 completed: 2026-08-20 (started 2026-08-19T07:01Z, ~31h36m; loop had 4 local DNS blips; fresh `--once` PASS; advanced to n100 2026-08-20T14:37Z)
- [x] Soak n100 completed: 2026-08-22 (started 2026-08-20T14:37Z, ~37h; loop had 401-before-token + DNS blips; fresh `--once` PASS 2026-08-22T03:39Z)
- [x] Neural performance metrics within threshold for n10/n25/n50/n100 (5xx=0, error_rate=0, cache ~98%; p95 series empty → WARN allowed)

Production RLHF (`scripts/gate10h_prod_rlhf.py`): `--stage check` **PASS** 2026-08-22; `--stage blueprint --confirm-rlhf` applied locally. Next: PR + Render Sync, then `--stage verify --assume-synced`. Kill/autotune stay OFF (Gate 10I/10J still stubs).

## Feature flags (repo truth)

Use Blueprint / Render env — **not** ad-hoc `FEATURE_NEURAL` / `FEATURE_RLHF`:

| Env | Purpose | Default prod |
| --- | --- | --- |
| `FEATURE_NEURAL_BANDIT` | Allow neural bandit agent | `false` |
| `FEATURE_RLHF_ROUTER` | Allow RLHF policy agent | `false` |
| `BANDIT_POLICY` | Active policy: `rule` \| `linucb` \| `neural` \| `rlhf` | `linucb` |

Runtime switch (after flags enabled): `POST /admin/bandit/switch_policy` with `{"policy":"neural"|"rlhf"|"linucb"|"rule"}`.  
If neural/RLHF not ready, service falls back to LinUCB with an explicit reason.

## Neural evaluation (`FEATURE_NEURAL_BANDIT`)

### Quality

- [x] Offline / staging benchmark vs LinUCB baseline (`POST /admin/benchmark/run`) — PASS on staging 2026-08-13
- [ ] Human review of routing decisions (sample ≥ N traces)
- [ ] A/B or canary cohort: neural vs `linucb` (holdout or sticky canary)
- [ ] Edge cases: cold start, missing features, provider failure → safe fallback
- [ ] No increase in harmful / unsafe recommendation paths

### Performance

- [ ] Decision latency acceptable (bandit choose path; target p95 decision overhead modest vs LinUCB)
- [ ] No material regression on `/search` / `/recommendations` p95 (baseline + 10%)
- [ ] Token / LLM cost within budget if neural path increases live calls
- [ ] Router cache hit rate stays healthy (target **&gt; 60%** when cache enabled)

### Safety

- [ ] Feature remains off in Blueprint until checklist sign-off
- [ ] Policy switch requires admin token; audited
- [ ] Rate limiting still effective (`/admin/rate-limit/status`)
- [ ] Kill switch still **not** required for this gate (stay OFF until Gate 10I)

## RLHF evaluation (`FEATURE_RLHF_ROUTER`)

### Training / readiness

- [ ] RLHF policy trained or seeded with recent feedback / reward data
- [ ] Reward / preference signal quality reviewed (accuracy / agreement target **&gt; 85%** if reward model used)
- [ ] KL / policy divergence vs baseline within agreed bounds
- [ ] Agent reports `ready=true` before controlling production traffic

### Online evaluation

- [x] Enable flag on **staging** first via `gate10h_staging_rlhf_drill.py`; switch policy to `rlhf`; smoke + benchmark — **PASS** 2026-08-13
- [ ] Production: enable `FEATURE_RLHF_ROUTER=true` via Blueprint + Sync **only after** prod neural stable (one flag at a time)
- [ ] Canary / A/B: route **≤ 10%** sticky cohort to RLHF (or admin switch with limited exposure)
- [ ] Human preference / reward ≥ baseline; no quality degradation for ≥ 24h
- [ ] Only then consider `BANDIT_POLICY=rlhf` (or 100% cohort) with explicit sign-off

## Enablement sequence (after checks pass)

1. Staging Neural — **DONE** (`gate10h_staging_neural.py`)
2. Prod prereq metrics — **DONE** (`gate10h_check_prod_prereq.py`)
3. Staging RLHF — `gate10h_staging_rlhf_drill.py` (next)
4. Production Neural — `gate10h_prod_neural.py` (one flag; soak n10→n25→n50→n100)
5. Production RLHF — only after prod neural stable (separate Blueprint apply; not in prod neural script)
6. Then Gate **10I** / **10J** (docs stubs only; do not enable yet)

### Operator commands

```bash
export STAGING_ADMIN_TOKEN=...
export PROD_ADMIN_TOKEN=...

# --- Staging Neural (done) ---
make gate10h-staging-neural ARGS='--stage evaluate --assume-synced --report'

# --- Staging RLHF (next) ---
make gate10h-staging-rlhf ARGS='--stage check --skip-prod-prereqs'
make gate10h-staging-rlhf ARGS='--stage setup --dry-run'
make gate10h-staging-rlhf ARGS='--stage setup'            # FEATURE_RLHF_ROUTER=true
# Sync staging, then:
make gate10h-staging-rlhf ARGS='--stage evaluate --assume-synced --report'
make gate10h-staging-rlhf ARGS='--stage cleanup'

# --- Production Neural (after staging RLHF PASS) ---
make gate10h-prod-neural ARGS='--stage check'
make gate10h-prod-neural ARGS='--stage dry-run'
make gate10h-prod-neural ARGS='--stage apply --confirm-neural'
# Sync production, then:
make gate10h-prod-neural ARGS='--stage verify --assume-synced'
make gate10h-prod-neural ARGS='--stage switch-neural --confirm-switch'
make gate10h-prod-neural ARGS='--stage start-soak --phase n10 --report'
# After ≥24h each: --stage advance --phase n25|n50|n100
make gate10h-prod-neural ARGS='--stage status --report'
# Surgical rollback (does not disable FEATURE_AI_ROUTER):
make gate10h-prod-neural ARGS='--stage rollback --confirm-rollback'
```

Blueprint: staging `render.yaml` / prod `render-production.yaml`.  
Validate production with `--allow-neural-bandit --allow-rlhf-router --allow-rlhf-after-neural` (both flags after n100 only).

## Rollback plan

If neural/RLHF fails any check:

1. **Immediate:** `POST /admin/bandit/switch_policy` → `{"policy":"linucb"}` (or `rule`)
2. **Env:** Blueprint `FEATURE_NEURAL_BANDIT=false` and/or `FEATURE_RLHF_ROUTER=false`, `BANDIT_POLICY=linucb` → Sync
3. **Do not** default to `FEATURE_AI_ROUTER=false` unless live router itself is implicated (prefer surgical rollback)
4. Escalate to AI / ops; file notes in this doc + rollout report
5. Optional: canary rollback via `scripts/gate10e_rollout.py --phase rollback` only if traffic-level incident

## Monitoring windows

| Signal | Where |
| --- | --- |
| Router / provider errors & cost | `/metrics`, `/admin/router/metrics`, `/admin/models/status` |
| Bandit policy / ready | `/admin/bandit/status`, switch_policy responses |
| Latency / 5xx / cache | `scripts/gate10h_monitor_soak.py` → `artifacts/gate10h_soak_monitor_{phase}.jsonl` |
| Safety | `/admin/safety/status` (must stay kill/autotune OFF) |

Soak n100 **PASS** 2026-08-22T03:39Z. Production RLHF Blueprint applied locally — Sync before `--stage verify`. Do not enable Gate 10I/10J.

## Sign-off

- [ ] AI Lead review  
- [ ] Ops review  
- [ ] Security review  
- [ ] Checklist items above complete for the policy being enabled  

## Next steps (after Gate 10H passes)

- Gate **10I** — Kill switch — stub: `docs/GATE_10I_KILL_SWITCH_CHECKLIST.md` (**do not enable yet**)
- Gate **10J** — Auto-tune — stub: `docs/GATE_10J_AUTO_TUNE_CHECKLIST.md` (**do not enable yet**)

## Artifacts / references

- `docs/GATE_10G_CLOSEOUT.md` — live + Chinese complete  
- `docs/GATE_10E_CLOSEOUT.md` — neural/RLHF human-only rule  
- `docs/GATE_10_PLAN.md` — flag sequence  
- `docs/RUNBOOK.md` §3g / §3h  
- Scripts: `gate10h_check_prod_prereq.py`, `gate10h_staging_neural.py`, `gate10h_staging_rlhf_drill.py`, `gate10h_prod_neural.py`, `gate10h_monitor_soak.py`, `gate10h_advance_neural.py`, `gate10h_prod_rlhf.py`
- Admin: `/admin/bandit/switch_policy`, `/admin/benchmark/*`
