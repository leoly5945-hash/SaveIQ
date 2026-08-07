.PHONY: recommendation-eval staging-provision-validate staging-provision-validate-template staging-seed-mock staging-smoke production-provision-validate production-smoke deploy-production security-scan gate10d-abtest-rollout gate10e-rollout

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
