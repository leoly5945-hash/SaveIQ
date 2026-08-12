.PHONY: recommendation-eval staging-provision-validate staging-provision-validate-template staging-seed-mock staging-smoke production-provision-validate production-smoke deploy-production security-scan gate10d-abtest-rollout gate10e-rollout gate10e-auto-rollout gate10f-flip-router gate10g-live-providers gate10h-staging-neural

PYTHON ?= python3

staging-provision-validate:
	$(PYTHON) scripts/validate_render_blueprint.py render.yaml

staging-provision-validate-template:
	$(PYTHON) scripts/validate_render_blueprint.py render.yaml --allow-placeholders

production-provision-validate:
	$(PYTHON) scripts/validate_render_blueprint.py render-production.yaml --profile production

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
