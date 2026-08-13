# Gate 10I: Kill Switch Enablement Checklist

Generated: 2026-08-13  
Status: **NOT STARTED** — prepare only after Gate 10H (neural + RLHF) is stable in production.

## Scope

Enable `FEATURE_KILL_SWITCH=true` with operator-reviewed thresholds. Auto-tune remains **OFF** until Gate 10J.

## Preconditions

- [ ] Gate 10H production Neural stable ≥ 24h (or explicitly deferred with sign-off)
- [ ] Gate 10H staging RLHF drill PASS; production RLHF either ON and stable or explicitly deferred
- [ ] Kill switch still OFF; not tripped
- [ ] `/admin/safety/status` thresholds reviewed (error rate, latency p95, cost)

## Enablement (sketch — do not run until Gate 10H closed)

1. Staging drill: enable kill env → trip → disarm → restore canary/policy
2. Production Blueprint: `FEATURE_KILL_SWITCH=true` (auto-tune stays false)
3. Sync → verify `/admin/safety/status` armed
4. Document trip actions and on-call runbook

## Out of scope

- `FEATURE_AUTO_TUNING` (Gate 10J)
- Auto-flipping neural / RLHF / `BANDIT_POLICY` (human-only forever)

## References

- `docs/GATE_10H_NEURAL_RLHF_CHECKLIST.md`
- `docs/GATE_10E_CLOSEOUT.md` (human-only flag rule)
- `docs/RUNBOOK.md` safety section
