#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
API_KEY="${2:-}"
TIMEOUT=10

fail() {
    echo "HEALTHCHECK FAIL: $*"
    exit 1
}

echo "=== TITAN X Health Check ==="
echo "Target: ${BASE_URL}"
echo "Time:   $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""

# 1. Liveness probe
echo -n "Liveness probe ... "
liveness=$(curl -sf --max-time "${TIMEOUT}" "${BASE_URL}/health/live" 2>&1) || fail "liveness endpoint unreachable"
echo "OK"

# 2. Readiness probe
echo -n "Readiness probe ... "
readiness=$(curl -sf --max-time "${TIMEOUT}" "${BASE_URL}/health/ready" 2>&1) || fail "readiness endpoint unreachable"
echo "OK"

# 3. Version endpoint
echo -n "Version check ... "
version=$(curl -sf --max-time "${TIMEOUT}" -H "X-API-Key: ${API_KEY}" "${BASE_URL}/api/v1/version" 2>&1) || fail "version endpoint unreachable"
echo "OK (${version})"

# 4. Auth endpoint (should return 401 without token)
echo -n "Auth required check ... "
status=$(curl -s -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" "${BASE_URL}/api/v1/users/me" 2>&1)
if [ "${status}" = "401" ] || [ "${status}" = "403" ]; then
    echo "OK (auth enforced: ${status})"
else
    fail "auth endpoint returned ${status}, expected 401/403"
fi

# 5. API documentation accessible
echo -n "Docs endpoint ... "
docs_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" "${BASE_URL}/docs" 2>&1)
if [ "${docs_status}" = "200" ] || [ "${docs_status}" = "302" ]; then
    echo "OK (${docs_status})"
else
    echo "WARN: docs returned ${docs_status}"
fi

# 6. Response time check
echo -n "Response time ... "
start=$(date +%s%N)
curl -sf --max-time "${TIMEOUT}" "${BASE_URL}/health/live" > /dev/null 2>&1
end=$(date +%s%N)
elapsed=$(( (end - start) / 1000000 ))
if [ "${elapsed}" -lt 500 ]; then
    echo "OK (${elapsed}ms)"
else
    echo "WARN: slow response (${elapsed}ms)"
fi

# 7. Database connectivity (via ready probe which checks DB)
echo -n "Database connectivity ... "
db_check=$(curl -sf --max-time "${TIMEOUT}" "${BASE_URL}/health/ready" 2>&1) || fail "database check failed"
echo "OK"

echo ""
echo "=== All health checks passed ==="
exit 0
