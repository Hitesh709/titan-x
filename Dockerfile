FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

COPY src ./src
RUN python -m compileall -q src

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000

WORKDIR /app

RUN addgroup --system titan && adduser --system --ingroup titan titan && \
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
COPY --from=builder /build/src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && chown -R titan:titan /app

USER titan
EXPOSE 8000

LABEL org.opencontainers.image.title="TITAN X API" \
      org.opencontainers.image.description="Production trading intelligence platform" \
      org.opencontainers.image.version="0.1.0"

ENTRYPOINT ["/entrypoint.sh"]
