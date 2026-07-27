#!/usr/bin/env bash
set -euo pipefail

APP_NAME="titan-x"
ENVIRONMENT="${1:-staging}"
COMPOSE_FILE="docker-compose.prod.yml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEPLOY_LOG="/var/log/${APP_NAME}/deploy-${TIMESTAMP}.log"

mkdir -p "/var/log/${APP_NAME}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${DEPLOY_LOG}"
}

log "=== Deploying ${APP_NAME} to ${ENVIRONMENT} ==="

log "Pulling latest images..."
docker compose -f "${COMPOSE_FILE}" pull >> "${DEPLOY_LOG}" 2>&1

log "Running database migrations..."
docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head >> "${DEPLOY_LOG}" 2>&1

log "Starting services..."
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans >> "${DEPLOY_LOG}" 2>&1

log "Waiting for health check..."
for i in $(seq 1 12); do
    if curl -sf http://localhost/health/ready > /dev/null 2>&1; then
        log "Health check passed"
        break
    fi
    if [ "${i}" -eq 12 ]; then
        log "ERROR: Health check failed after 60 seconds"
        docker compose -f "${COMPOSE_FILE}" logs --tail=50 api >> "${DEPLOY_LOG}" 2>&1
        exit 1
    fi
    sleep 5
done

log "Cleaning up old images..."
docker system prune -f --filter "until=24h" >> "${DEPLOY_LOG}" 2>&1

log "=== Deployment to ${ENVIRONMENT} complete ==="
log "Services:"
docker compose -f "${COMPOSE_FILE}" ps
