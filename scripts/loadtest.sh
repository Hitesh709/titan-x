#!/usr/bin/env bash
set -euo pipefail

echo "=== TITAN X Load Test ==="
TARGET="${1:-http://localhost:8000}"
DURATION="${2:-60}"
USERS="${3:-10}"
SPAWN_RATE="${4:-1}"

if ! command -v locust &> /dev/null; then
    echo "Installing locust..."
    pip install locust
fi

echo "Target:     ${TARGET}"
echo "Duration:   ${DURATION}s"
echo "Users:      ${USERS}"
echo "Spawn rate: ${SPAWN_RATE}/s"

locust \
    --host="${TARGET}" \
    --locustfile=tests/load/locustfile.py \
    --users="${USERS}" \
    --spawn-rate="${SPAWN_RATE}" \
    --run-time="${DURATION}s" \
    --headless \
    --only-summary \
    --csv=tests/load/reports/loadtest
