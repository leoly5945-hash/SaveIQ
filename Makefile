.PHONY: recommendation-eval staging-provision-validate staging-provision-validate-template staging-seed-mock staging-smoke production-provision-validate production-smoke deploy-production security-scan gate10d-abtest-rollout gate10e-rollout gate10e-auto-rollout gate10f-flip-router gate10g-live-providers gate10h-staging-neural gate10h-check-prod-prereq gate10h-staging-rlhf gate10h-prod-neural gate10h-monitor-soak gate10h-advance-neural gate10h-prod-rlhf gate10i-kill-switch gate10j-auto-tune

PYTHON ?= python3

staging-provision-validate:
	$(PYTHON) scripts/validate_render_blueprint.py render.yaml

staging-provision-validate-template:
	$(PYTHON) scripts/validate_render_blueprint.py render.yaml --allow-placeholders

production-provision-validate:
	$(PYTHON) scripts/validate_render_blueprint.py render-production.yaml --profile production --allow-neural-bandit --allow-rlhf-router --allow-rlhf-after-neural --allow-kill-switch

staging-seed-mock:
	$(PYTHON) scripts/staging_seed_mock.py

staging-smoke:
	$(PYTHON) scripts/staging_smoke.py

production-smoke:
	$(PYTHON) scripts/production_smoke.py

deploy-production:
	bash scripts/deploy_production.sh

security-scan:
	bash scripts/security_scan.sh

recommendation-eval:
	$(PYTHON) scripts/evaluate_recommendations.py

# Gate 10D: merge/publish/pin/deploy/smoke/A-B probe (never mutates canary).
# Requires ADMIN_API_TOKEN. Optional: RENDER_API_KEY + RENDER_SERVICE_ID_API/WEB.
gate10d-abtest-rollout:
	$(PYTHON) scripts/gate10d_abtest_rollout.py

# Gate 10E: staging drill → C3 → soak → C4 → soak → mock router.
# Requires STAGING_ADMIN_TOKEN + PROD_ADMIN_TOKEN. Pass args after -- .
# Example: make gate10e-rollout -- --phase staging_drill
gate10e-rollout:
	$(PYTHON) scripts/gate10e_rollout.py $(ARGS)

# Gate 10E background auto-rollout (waits C3 soak → C4 → C4 soak).
# Requires PROD_ADMIN_TOKEN.
#   make gate10e-auto-rollout ARGS='--status'
#   make gate10e-auto-rollout ARGS='--daemon'
gate10e-auto-rollout:
	$(PYTHON) scripts/gate10e_auto_rollout.py $(ARGS)

# Gate 10F: flip FEATURE_AI_ROUTER=true with AI_ROUTER_MODE=mock (Blueprint edit).
#   make gate10f-flip-router ARGS='--check'
#   make gate10f-flip-router ARGS='--dry-run'
#   make gate10f-flip-router ARGS='--apply'
gate10f-flip-router:
	$(PYTHON) scripts/gate10f_flip_router.py $(ARGS)

# Gate 10G: evaluate / enable live AI router + Chinese LLM providers.
#   make gate10g-live-providers ARGS='--check'
#   make gate10g-live-providers ARGS='--evaluate'
#   make gate10g-live-providers ARGS='--dry-run'
#   make gate10g-live-providers ARGS='--apply --confirm-live --confirm-chinese --ack-tos --ack-pii --ack-cost-budget --ack-keys-in-render'
gate10g-live-providers:
	$(PYTHON) scripts/gate10g_live_providers.py $(ARGS)

# Gate 10H: staging Neural Bandit evaluation (human-only).
#   make gate10h-staging-neural ARGS='--stage check'
#   make gate10h-staging-neural ARGS='--stage setup --dry-run'
#   make gate10h-staging-neural ARGS='--stage setup'
#   make gate10h-staging-neural ARGS='--stage evaluate --assume-synced'
#   make gate10h-staging-neural ARGS='--stage cleanup'
gate10h-staging-neural:
	$(PYTHON) scripts/gate10h_staging_neural.py $(ARGS)

# Gate 10H: production prereq before neural (Prometheus /metrics + admin safety/router).
#   make gate10h-check-prod-prereq ARGS='--warm-endpoints --capture-baseline'
#   make gate10h-check-prod-prereq ARGS='--baseline artifacts/gate10h_prod_baseline.json --allow-sparse-llm --allow-sparse-latency --report'
gate10h-check-prod-prereq:
	$(PYTHON) scripts/gate10h_check_prod_prereq.py $(ARGS)

# Gate 10H: staging RLHF drill (human-only; neural flag must stay false).
#   make gate10h-staging-rlhf ARGS='--stage check --skip-prod-prereqs'
#   make gate10h-staging-rlhf ARGS='--stage setup --dry-run'
#   make gate10h-staging-rlhf ARGS='--stage setup'
#   make gate10h-staging-rlhf ARGS='--stage evaluate --assume-synced --report'
#   make gate10h-staging-rlhf ARGS='--stage cleanup'
gate10h-staging-rlhf:
	$(PYTHON) scripts/gate10h_staging_rlhf_drill.py $(ARGS)

# Gate 10H: production Neural enablement (after staging RLHF PASS).
#   make gate10h-prod-neural ARGS='--stage check'
#   make gate10h-prod-neural ARGS='--stage dry-run'
#   make gate10h-prod-neural ARGS='--stage apply --confirm-neural'
#   make gate10h-prod-neural ARGS='--stage verify --assume-synced'
#   make gate10h-prod-neural ARGS='--stage switch-neural --confirm-switch'
#   make gate10h-prod-neural ARGS='--stage start-soak --phase n10 --report'
#   make gate10h-prod-neural ARGS='--stage rollback --confirm-rollback'
gate10h-prod-neural:
	$(PYTHON) scripts/gate10h_prod_neural.py $(ARGS)

# Gate 10H: production neural soak monitor (does not mutate flags/canary).
#   make gate10h-monitor-soak ARGS='--phase n10 --once --report'
#   make gate10h-monitor-soak ARGS='--phase n10 --duration 24h --interval 5m'
gate10h-monitor-soak:
	$(PYTHON) scripts/gate10h_monitor_soak.py $(ARGS)

# Gate 10H: advance neural soak n10→n25→n50→n100 (requires 24h + monitor PASS).
#   make gate10h-advance-neural ARGS='--stage status'
#   make gate10h-advance-neural ARGS='--phase n10 --target n25 --dry-run --report'
gate10h-advance-neural:
	$(PYTHON) scripts/gate10h_advance_neural.py $(ARGS)

# Gate 10H: production RLHF after neural n100 PASS.
#   make gate10h-prod-rlhf ARGS='--stage check'
#   make gate10h-prod-rlhf ARGS='--stage blueprint --dry-run'
gate10h-prod-rlhf:
	$(PYTHON) scripts/gate10h_prod_rlhf.py $(ARGS)

# Gate 10I: arm FEATURE_KILL_SWITCH (staging drill → prod). Autotune stays OFF.
#   make gate10i-kill-switch ARGS='--stage check'
#   make gate10i-kill-switch ARGS='--stage staging-blueprint --dry-run'
#   make gate10i-kill-switch ARGS='--stage staging-drill --assume-synced --confirm-trip'
#   make gate10i-kill-switch ARGS='--stage prod-verify --assume-synced'
gate10i-kill-switch:
	$(PYTHON) scripts/gate10i_kill_switch.py $(ARGS)

# Gate 10J: staging-only auto-tune dry-run. Never writes render-production.yaml.
# Never flips FEATURE_NEURAL_BANDIT / FEATURE_RLHF_ROUTER / BANDIT_POLICY.
#   make gate10j-auto-tune ARGS='--stage check'
#   make gate10j-auto-tune ARGS='--stage staging-dry-run'
#   make gate10j-auto-tune ARGS='--stage staging-dry-run --confirm-autotune'
#   make gate10j-auto-tune ARGS='--stage evaluate'
#   make gate10j-auto-tune ARGS='--stage cleanup --confirm-autotune'
gate10j-auto-tune:
	$(PYTHON) scripts/gate10j_auto_tune.py $(ARGS)
