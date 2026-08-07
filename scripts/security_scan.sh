#!/usr/bin/env bash
# Local dependency / security scan helper (Gate 10A).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

echo "==> Python dependency audit (pip-audit)"
"$PYTHON" -m pip install -q pip-audit
(
  cd apps/api
  "$PYTHON" -m pip install -q -e .
  "$PYTHON" -m pip_audit --progress-spinner=off
)

echo "==> Node dependency audit (npm audit)"
npm audit --audit-level=high

if command -v trivy >/dev/null 2>&1; then
  echo "==> Trivy filesystem scan"
  trivy fs --severity --scanners vuln --severity-exit-code 1 \
    --ignore-unfixed .
else
  echo "==> Trivy not installed; skipping local fs scan (CI runs aquasecurity/trivy-action)"
fi

echo "security_scan=ok"
