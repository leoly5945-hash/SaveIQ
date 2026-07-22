.PHONY: staging-provision-validate staging-provision-validate-template staging-seed-mock staging-smoke

PYTHON ?= python3

staging-provision-validate:
	$(PYTHON) scripts/validate_render_blueprint.py render.yaml

staging-provision-validate-template:
	$(PYTHON) scripts/validate_render_blueprint.py render.yaml --allow-placeholders

staging-seed-mock:
	$(PYTHON) scripts/staging_seed_mock.py

staging-smoke:
	$(PYTHON) scripts/staging_smoke.py
