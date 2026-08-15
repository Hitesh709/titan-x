#!/usr/bin/env sh
set -e

# Strip quotes from secrets if present
strip_quotes() {
    echo "$1" | tr -d '"'"'"'
}

echo "=== TITAN X Entrypoint ==="
echo "Environment: ${ENVIRONMENT:-production}"

# Render (and some hosts) hand over a `postgres://` or `postgresql://` URL, but
# SQLAlchemy's async engine requires the `postgresql+asyncpg://` driver. Rewrite
# the scheme so the connection works without manual intervention.
if [ -n "$DATABASE_URL" ]; then
    case "$DATABASE_URL" in
        postgresql+asyncpg://*|postgres+asyncpg://*) ;;
        postgres://*) DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgres://}" ;;
        postgresql://*) DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgresql://}" ;;
    esac
    export DATABASE_URL
fi

# Run database migrations on startup
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying database migrations..."
    alembic upgrade head
    echo "Migrations applied successfully."
else
    echo "Skipping migrations (RUN_MIGRATIONS=false)"
fi

# Validate critical env vars
if [ -z "$API_KEY" ] || [ "${#API_KEY}" -lt 32 ]; then
    echo "WARNING: API_KEY is missing or too short (min 32 chars)"
fi
if [ -z "$JWT_SECRET_KEY" ] || [ "${#JWT_SECRET_KEY}" -lt 64 ]; then
    echo "WARNING: JWT_SECRET_KEY is missing or too short (min 64 chars)"
fi

# Start Uvicorn
exec uvicorn titan_x.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${UVICORN_WORKERS:-4}" \
    --proxy-headers \
    --limit-concurrency "${UVICORN_LIMIT_CONCURRENCY:-1024}" \
    --backlog "${UVICORN_BACKLOG:-2048}" \
    --no-access-log \
    --timeout-keep-alive 30
