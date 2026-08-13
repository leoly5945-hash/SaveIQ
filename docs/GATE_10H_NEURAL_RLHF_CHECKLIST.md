# Gate 10H: Neural / RLHF Evaluation Checklist

Generated: 2026-08-10  
Updated: 2026-08-13 (staging Neural drill PASS)  
Status: PENDING for **production** enablement — staging Neural drill **PASS**; RLHF not started

This gate is **human-only**. Auto-tune (Gate 10E/10J) must never flip neural/RLHF or `BANDIT_POLICY`.

## Current production baseline (rechecked 2026-08-11)

| Flag / signal | Value |
| --- | --- |
| `FEATURE_AI_ROUTER` / mode | `active=True`, **`live`** |
| Chinese LLM | **ON** (`chinese=True`; DeepSeek configured) |
| `BANDIT_POLICY` / public bandit | `linucb`; `controls_routing=False` |
| `FEATURE_NEURAL_BANDIT` | `false` on prod (staging drill temporarily `true`, then cleaned up) |
| `FEATURE_RLHF_ROUTER` | `false` |
| Kill / autotune | **OFF**, not tripped |
| Canary | enabled **100%** |
| Smoke | `production_smoke=ok` (live + chinese allow flags) |

## Prerequisites

- [x] Gate 10E complete (C4 soak ≥24h, mock_router=ok) — see `docs/GATE_10E_ROLLOUT_REPORT.md`
- [x] Gate 10F complete (`FEATURE_AI_ROUTER=true`, mode=mock) — superseded by 10G
- [x] Gate 10G complete (`mode=live`, Chinese LLM ON, DeepSeek key present)
- [x] Live providers stable for ≥ **24h** after Gate 10G Sync (recheck 2026-08-11: smoke ok, live+chinese, no kill trip)
- [ ] Provider/router error rate within Gate 10 plan budgets (target: LLM/provider errors **&lt; 5%** of live calls; HTTP 5xx stay healthy) — **needs metrics review window** (`/metrics` LLM series still sparse)
- [ ] Latency within baseline + **10%** (p95 `/search` / `/recommendations` vs pre-10G window) — **needs baseline compare**
- [x] Kill switch / auto-tune still **OFF** (unchanged) — confirmed `/admin/safety/status`
- [x] Staging Neural drill: `gate10h_staging_neural.py` evaluate **PASS** (2026-08-13; neural reward &gt; linucb; cleanup → flag `false`)
- [ ] Staging RLHF drill: not started

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

- [ ] Enable flag on **staging** first; switch policy to `rlhf`; smoke + benchmark
- [ ] Production: enable `FEATURE_RLHF_ROUTER=true` via Blueprint + Sync (policy may stay `linucb` initially)
- [ ] Canary / A/B: route **≤ 10%** sticky cohort to RLHF (or admin switch with limited exposure)
- [ ] Human preference / reward ≥ baseline; no quality degradation for ≥ 24h
- [ ] Only then consider `BANDIT_POLICY=rlhf` (or 100% cohort) with explicit sign-off

## Enablement sequence (after checks pass)

Do **not** invent one-shot traffic scripts until they exist. Preferred path:

1. Staging: set `FEATURE_NEURAL_BANDIT=true` (and/or RLHF), Sync, `POST /admin/bandit/switch_policy`
2. Staging smoke + benchmark PASS  
3. Production Blueprint: enable **one** flag at a time (`FEATURE_NEURAL_BANDIT` first recommended)
4. Render Sync → verify `/admin/bandit/status` (or router/bandit admin surfaces)
5. Limited exposure (canary/A-B or careful policy switch) ≥ 24h  
6. Promote or rollback  
7. Repeat for RLHF only after neural (or LinUCB) is stable

### Operator commands (sketch)

```bash
export STAGING_ADMIN_TOKEN=...
export PROD_ADMIN_TOKEN=...

# Automated staging path (preferred)
make gate10h-staging-neural ARGS='--stage check'
make gate10h-staging-neural ARGS='--stage setup'            # FEATURE_NEURAL_BANDIT=true in render.yaml
# Sync staging Blueprint on Render, then:
make gate10h-staging-neural ARGS='--stage evaluate --assume-synced --report'
make gate10h-staging-neural ARGS='--stage cleanup'

# Manual policy switch (after flag enabled + Sync)
curl -sS -X POST -H "X-Admin-Token: $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"policy":"neural"}' \
  "https://dealhunter-staging-api.onrender.com/admin/bandit/switch_policy"

# Rollback policy without disabling AI router:
curl -sS -X POST -H "X-Admin-Token: $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"policy":"linucb"}' \
  "https://dealhunter-staging-api.onrender.com/admin/bandit/switch_policy"
```

Blueprint edits (staging first): `FEATURE_NEURAL_BANDIT` in `render.yaml` → validate with `--allow-neural-bandit` → Sync.  
Production enablement remains a separate signed checklist step after staging PASS.

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
| Latency / 5xx | Render metrics, Prometheus SLIs |
| Safety | `/admin/safety/status` (must stay kill/autotune OFF) |

## Sign-off

- [ ] AI Lead review  
- [ ] Ops review  
- [ ] Security review  
- [ ] Checklist items above complete for the policy being enabled  

## Next steps (after Gate 10H passes)

- Gate **10I** — Kill switch enablement (`FEATURE_KILL_SWITCH`) — separate checklist  
- Gate **10J** — Auto-tune enablement (`FEATURE_AUTO_TUNING`) — separate checklist; still must not auto-flip neural/RLHF  

## Artifacts / references

- `docs/GATE_10G_CLOSEOUT.md` — live + Chinese complete  
- `docs/GATE_10E_CLOSEOUT.md` — neural/RLHF human-only rule  
- `docs/GATE_10_PLAN.md` — flag sequence  
- `docs/RUNBOOK.md` §3g / §3h  
- Admin: `/admin/bandit/switch_policy`, `/admin/benchmark/*`
