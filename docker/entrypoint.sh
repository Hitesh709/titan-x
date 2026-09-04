#!/usr/bin/env sh
set -e

echo "=== TITAN X Entrypoint ==="
echo "Environment: ${ENVIRONMENT:-production}"

echo "Database: ${DATABASE_URL:-sqlite+aiosqlite:///./titan_x.db}"

# The application creates/updates its SQLite schema during startup.
# Keep Alembic optional so legacy database-specific migrations cannot block
# the SQLite deployment.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "Applying database migrations..."
    alembic upgrade head
    echo "Migrations applied successfully."
else
    echo "Skipping Alembic migrations (SQLite startup schema management enabled)."
fi

if [ -z "$API_KEY" ] || [ "${#API_KEY}" -lt 32 ]; then
    echo "WARNING: API_KEY is missing or too short (min 32 chars)"
fi
if [ -z "$JWT_SECRET_KEY" ] || [ "${#JWT_SECRET_KEY}" -lt 64 ]; then
    echo "WARNING: JWT_SECRET_KEY is missing or too short (min 64 chars)"
fi

exec uvicorn titan_x.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${UVICORN_WORKERS:-1}" \
    --proxy-headers \
    --limit-concurrency "${UVICORN_LIMIT_CONCURRENCY:-1024}" \
    --backlog "${UVICORN_BACKLOG:-2048}" \
    --no-access-log \
    --timeout-keep-alive 30
