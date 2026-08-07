#!/usr/bin/env bash
# Trigger / document a production deploy for saveiq-production (Gate 10A).
#
# Production auto-deploy is OFF in render-production.yaml. This script helps operators
# pin digests and reminds them to sync the Blueprint / clear deploy in Render.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
BLUEPRINT="${BLUEPRINT:-render-production.yaml}"

echo "==> Validate production Blueprint"
"$PYTHON" scripts/validate_render_blueprint.py "$BLUEPRINT" --profile production

API_DIGEST="$(grep -Eo 'saveiq-engine@sha256:[a-f0-9]{64}' "$BLUEPRINT" | head -1 || true)"
WEB_DIGEST="$(grep -Eo 'saveiq-web@sha256:[a-f0-9]{64}' "$BLUEPRINT" | head -1 || true)"

echo "pinned_api=${API_DIGEST:-unknown}"
echo "pinned_web=${WEB_DIGEST:-unknown}"

if [[ -z "${RENDER_API_KEY:-}" ]]; then
  cat <<'EOF'
deploy_production=manual

Render CLI/API key not set. Apply or sync the Blueprint in the dashboard:

1. Confirm digests in render-production.yaml match a CI-published GHCR image.
2. Render → Blueprints → saveiq-production → Sync / Apply.
3. Set secrets (ADMIN_API_TOKEN, provider keys) if prompted — never commit them.
4. Wait for dealhunter-production-api and dealhunter-production-web healthy.
5. Run: ADMIN_API_TOKEN=... PYTHON=.venv/bin/python make production-smoke

Optional: export RENDER_API_KEY and re-run to use Render API deploy hooks when configured.
EOF
  exit 0
fi

if ! command -v render >/dev/null 2>&1 && ! command -v curl >/dev/null 2>&1; then
  echo "deploy_production=error: need render CLI or curl" >&2
  exit 1
fi

cat <<EOF
deploy_production=api_key_present

Automated Render deploy hooks are environment-specific.
Use the Render dashboard Sync for blueprint $BLUEPRINT, then:

  ADMIN_API_TOKEN=... API_URL=https://dealhunter-production-api.onrender.com \\
    WEB_URL=https://dealhunter-production-web.onrender.com \\
    PYTHON=.venv/bin/python make production-smoke
EOF
