#!/usr/bin/env bash
# Local dependency / security scan helper (Gate 10A).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

echo "==> Python dependency audit (pip-audit on runtime deps)"
"$PYTHON" -m pip install -q pip-audit
"$PYTHON" - <<'PY'
from pathlib import Path
import tomllib

data = tomllib.loads(Path("apps/api/pyproject.toml").read_text(encoding="utf-8"))
Path("apps/api/requirements-audit.txt").write_text(
    "\n".join(data["project"]["dependencies"]) + "\n",
    encoding="utf-8",
)
PY
"$PYTHON" -m pip_audit -r apps/api/requirements-audit.txt --progress-spinner=off
rm -f apps/api/requirements-audit.txt

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
