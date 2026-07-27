#!/usr/bin/env bash
set -euo pipefail

APP_NAME="titan-x"
ENVIRONMENT="${1:-staging}"
COMPOSE_FILE="docker-compose.prod.yml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ROLLBACK_LOG="/var/log/${APP_NAME}/rollback-${TIMESTAMP}.log"

mkdir -p "/var/log/${APP_NAME}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${ROLLBACK_LOG}"
}

log "=== Rolling back ${APP_NAME} on ${ENVIRONMENT} ==="

# Stop current services
log "Stopping current services..."
docker compose -f "${COMPOSE_FILE}" down --timeout 30 >> "${ROLLBACK_LOG}" 2>&1

# Rollback API to previous tag
PREVIOUS_TAG="${2:-latest}"
log "Rolling back to image tag: ${PREVIOUS_TAG}"

# Update docker-compose override with previous tag
cat > docker-compose.override.yml << EOF
services:
  api:
    image: ghcr.io/anomalyco/titan-x:${PREVIOUS_TAG}
  worker:
    image: ghcr.io/anomalyco/titan-x-worker:${PREVIOUS_TAG}
EOF

log "Pulling previous images..."
docker compose -f "${COMPOSE_FILE}" pull >> "${ROLLBACK_LOG}" 2>&1

log "Running previous migrations (downgrade if needed)..."
# Note: manual downgrade may be needed for schema-breaking changes

log "Starting services with previous version..."
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans >> "${ROLLBACK_LOG}" 2>&1

log "Waiting for health check..."
sleep 10
if curl -sf http://localhost/health/ready > /dev/null 2>&1; then
    log "Health check passed after rollback"
else
    log "ERROR: Health check failed after rollback"
    docker compose -f "${COMPOSE_FILE}" logs --tail=50 api
    exit 1
fi

log "Removing override file..."
rm -f docker-compose.override.yml

log "=== Rollback to ${PREVIOUS_TAG} complete ==="
