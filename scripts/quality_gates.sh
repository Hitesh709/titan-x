#!/usr/bin/env bash
set -euo pipefail

# Xecaps production quality gate runner.
# Run from repository root. Each command is intentionally fail-fast.

if [[ -d web ]]; then
  echo '== Frontend: typecheck =='
  (cd web && npm run typecheck)
  echo '== Frontend: production build =='
  (cd web && npm run build)
fi

if [[ -f pyproject.toml ]]; then
  echo '== Backend: ruff =='
  ruff check src tests
  echo '== Backend: formatting =='
  ruff format --check src tests
fi

echo '== Security: Bandit =='
bandit -q -r src

echo '== Security: dependency audit =='
pip-audit

echo '== Quality gates passed =='
