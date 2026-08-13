# Gate 10J: Auto-Tune Enablement Checklist

Generated: 2026-08-13  
Status: **NOT STARTED** — only after Gate 10I kill switch is proven.

## Scope

Enable `FEATURE_AUTO_TUNING` (prefer dry-run first) for capped hparam adjustments. Must **never** flip:

- `FEATURE_NEURAL_BANDIT`
- `FEATURE_RLHF_ROUTER`
- `BANDIT_POLICY`

## Preconditions

- [ ] Gate 10I kill switch armed and exercised (staging + prod drill)
- [ ] Auto-tune still OFF in Blueprint
- [ ] Cap bounds reviewed (`AUTO_TUNE_*` settings)
- [ ] Prefer `AUTO_TUNE_DRY_RUN=true` for first production window

## Enablement (sketch)

1. Staging: auto-tune dry-run → observe propose events
2. Production Blueprint: enable with dry-run → Sync → monitor
3. Only then consider dry-run=false with explicit sign-off
4. Confirm human-only flags remain untouched after soak

## References

- `docs/GATE_10I_KILL_SWITCH_CHECKLIST.md`
- `docs/GATE_10E_CLOSEOUT.md`
- `apps/api/app/services/safety/service.py` (`HUMAN_ONLY_FLAGS`)
