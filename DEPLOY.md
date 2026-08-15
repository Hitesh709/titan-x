# Deploy — TITAN X Production Deployment Guide

## Automated Backups (Render free tier)

Render's free Postgres database is **deleted after 90 days**, so automated backups
are essential. TITAN X runs a backup **inside the API process** (no paid cron job):
every `BACKUP_INTERVAL_HOURS` it runs `pg_dump`, compresses the result, and uploads
it to an S3-compatible bucket (AWS S3, Cloudflare R2, MinIO, …).

### Enable backups

1. Create an S3-compatible bucket (Cloudflare R2 is free: 10 GB). Note the
   endpoint (e.g. `https://<id>.r2.cloudflarestorage.com`), bucket name, region,
   and an access key/secret.
2. In the Render dashboard, on the `titan-x-api` service → **Environment**, set:

   | Key                     | Value                                  |
   |-------------------------|----------------------------------------|
   | `BACKUP_ENABLED`        | `true`                                 |
   | `BACKUP_INTERVAL_HOURS` | `24`                                   |
   | `BACKUP_S3_PREFIX`      | `titan-x-backups`                      |
   | `BACKUP_S3_ENDPOINT`    | your endpoint                          |
   | `BACKUP_S3_BUCKET`      | your bucket name                       |
   | `BACKUP_S3_REGION`      | `auto` (R2) or your region            |
   | `BACKUP_S3_ACCESS_KEY`  | secret (`sync: false`)                 |
   | `BACKUP_S3_SECRET_KEY`  | secret (`sync: false`)                 |

3. Redeploy. Backups appear at `titan-x-backups/titan-x-<timestamp>.sql.gz`.

> Note: the free web service sleeps after 15 min idle, so the backup loop only
> fires while it's awake. For a quiet app you'll get a backup each time it's
> visited, not strictly every 24h. Use a paid always-on instance for guaranteed
> cadence.

### Admin endpoints (require `X-API-Key` + admin JWT)

- `GET  /api/v1/admin/backup/list` — list available backups.
- `GET  /api/v1/admin/backup/download?key=<key>` — download a backup file
  (`application/gzip`) directly, e.g.:

  ```bash
  curl -L "https://titan-x.onrender.com/api/v1/admin/backup/download?key=titan-x-backups/titan-x-<ts>.sql.gz" \
    -H "Authorization: Bearer <ADMIN_JWT>" -H "X-API-Key: <API_KEY>" -o backup.sql.gz
  ```

- `POST /api/v1/admin/backup/restore` — restore the latest backup, or a specific
  one via `{ "key": "titan-x-backups/titan-x-<ts>.sql.gz" }`.

  Restore is **disruptive** (it drops/recreates database objects). Example:

  ```bash
  curl -X POST "https://titan-x.onrender.com/api/v1/admin/backup/restore" \
    -H "Authorization: Bearer <ADMIN_JWT>" \
    -H "X-API-Key: <API_KEY>" \
    -H "Content-Type: application/json" \
    -d '{}'
  ```

### Manual restore (alternative)

```bash
# Download from your bucket, then:
gunzip -c titan-x-<ts>.sql.gz | psql "$DATABASE_URL"
```

---

## Prerequisites

- Docker 24+ & Docker Compose v2
- Python 3.13+ (for local tooling)
- PostgreSQL 17+ (or use Docker image)
- Redis 7+ (or use Docker image)
- Domain name with DNS pointing to server
- SSL certificate (Let's Encrypt or commercial CA)
- GitHub Container Registry access (or alternative registry)

---

## Infrastructure

### Production Stack

| Service    | Role                    | Replicas |
|------------|-------------------------|----------|
| Nginx      | Reverse proxy, TLS     | 1        |
| API        | FastAPI application     | 2+       |
| Worker     | Background task worker  | 2+       |
| Scheduler  | Cron job dispatcher     | 1        |
| PostgreSQL | Primary database        | 1        |
| Redis      | Cache, queue, sessions  | 1        |

---

## Quick Deploy

### 1. Clone & Configure
```bash
git clone https://github.com/anomalyco/titan-x.git /opt/titan-x
cd /opt/titan-x

# Copy and edit environment
cp env/prod.env .env
# Edit .env with your secrets:
#   API_KEY=<64-char-random>
#   JWT_SECRET_KEY=<64-char-random>
#   POSTGRES_PASSWORD=<strong-password>
#   REDIS_PASSWORD=<strong-password>
```

### 2. Start Services
```bash
# Pull latest images
docker compose -f docker-compose.prod.yml pull

# Run database migrations
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# Start all services
docker compose -f docker-compose.prod.yml up -d

# Verify health
curl http://localhost/health/ready
```

### 3. Verify
```bash
# Run smoke tests
pip install httpx pytest
pytest tests/smoke -v --base-url=http://localhost

# Run load test (optional)
bash scripts/loadtest.sh http://localhost 120 50 5
```

---

## Environment Configuration

| Variable                      | Production         | Staging            | Notes                        |
|-------------------------------|--------------------|--------------------|------------------------------|
| `ENVIRONMENT`                 | production         | staging            |                              |
| `DEBUG`                       | false              | false              | Never true in prod           |
| `DOCS_ENABLED`                | false              | true               |                              |
| `UVICORN_WORKERS`             | 4                  | 2                  | = 2× CPU cores               |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 15                 | 30                 | Lower is safer               |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | 1                  | 7                  |                              |
| `RATE_LIMIT_REQUESTS`         | 120                | 200                | Per minute                   |
| `BRUTE_FORCE_MAX_ATTEMPTS`    | 3                  | 5                  | Before lockout               |
| `DB_POOL_SIZE`                | 20                 | 10                 |                              |
| `DB_MAX_OVERFLOW`             | 40                 | 20                 |                              |

---

## CI/CD Pipeline

The GitHub Actions pipeline:

1. **CI** (`.github/workflows/ci.yml`) — on push/PR to main:
   - Lint with Ruff
   - Run unit + integration + smoke tests
   - Security scan (bandit, safety)
   - Build & push Docker images to GHCR

2. **Deploy** (`.github/workflows/deploy.yml`) — on CI success:
   - Deploy to staging
   - Verify staging health
   - Deploy to production (with Slack notification)
   - Verify production health

### Required GitHub Secrets

| Secret                  | Description                        |
|-------------------------|------------------------------------|
| `DEPLOY_HOST`           | SSH host for deployment server     |
| `DEPLOY_USER`           | SSH user                           |
| `DEPLOY_KEY`            | SSH private key                    |
| `SLACK_DEPLOY_WEBHOOK`  | Slack incoming webhook URL         |

---

## Database Migrations

```bash
# Apply all pending migrations
docker compose run --rm api alembic upgrade head

# Create a new migration
docker compose run --rm api alembic revision --autogenerate -m "description"

# Rollback one step
docker compose run --rm api alembic downgrade -1

# View history
docker compose run --rm api alembic history
```

---

## Monitoring & Alerting

### Health Endpoints

| Endpoint         | Purpose                    | Expected |
|------------------|----------------------------|----------|
| `/health/live`   | Liveness probe (k8s)       | 200      |
| `/health/ready`  | Readiness probe (DB check) | 200      |
| `/api/v1/monitoring/system` | Full system snapshot | 200 |

### Key Metrics to Monitor (via `/api/v1/monitoring/system`)
- **CPU**: Load average, percent utilization
- **Memory**: Available GB, percent usage
- **API Latency**: Average ms over last 5 minutes
- **Database**: Connection pool usage, ping time
- **Queue**: Running job count
- **Scheduler**: Failed executions, recent execution statuses

### Alert Thresholds (Recommended)

| Metric              | Warning        | Critical       |
|---------------------|----------------|----------------|
| CPU %               | > 70%          | > 90%          |
| Memory %            | > 75%          | > 90%          |
| API P95 Latency     | > 500ms        | > 2s           |
| 5xx Error Rate      | > 1%           | > 5%           |
| DB Pool Utilization | > 80%          | > 95%          |
| Queue Backlog       | > 100          | > 1000         |
| Failed Executions   | > 5/hour       | > 20/hour      |

---

## Backup & Recovery

### Database Backup
```bash
# Daily backup via cron
docker compose exec postgres pg_dump -U titan_x titan_x > /backups/titan_x_$(date +%Y%m%d).sql

# Restore
cat /backups/titan_x_20260722.sql | docker compose exec -T postgres psql -U titan_x titan_x
```

### Volume Backup
```bash
# Redis data
tar czf /backups/redis_$(date +%Y%m%d).tar.gz /var/lib/docker/volumes/titan-x_redis_data
```

---

## Rollback

```bash
# Automatic rollback to previous image tag
bash scripts/rollback.sh production <previous-sha>

# Manual rollback
docker compose -f docker-compose.prod.yml down
# Edit docker-compose.override.yml with old image tag
docker compose -f docker-compose.prod.yml up -d
```

---

## Scaling

### Horizontal (API workers)
```yaml
# docker-compose.prod.yml
deploy:
  replicas: 4
```

### Vertical (resource limits)
```yaml
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: 1G
```

### Database connection pooling
```
DB_POOL_SIZE=20       # Min connections
DB_MAX_OVERFLOW=40    # Burst connections
```

---

## Troubleshooting

### "Connection refused" on startup
PostgreSQL or Redis may not be ready yet. Check with:
```bash
docker compose logs postgres
docker compose logs redis
```

### Health check fails after deploy
```bash
docker compose logs api --tail=100
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/live').read())"
```

### Migration conflicts
```bash
docker compose run --rm api alembic history
docker compose run --rm api alembic downgrade -1
# Resolve conflict in migration file, then re-run
docker compose run --rm api alembic upgrade head
```

### High memory usage
- Reduce `UVICORN_WORKERS` to match CPU count
- Reduce `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`
- Check Redis memory with `INFO memory`
- Verify no memory leaks in custom services

---

## Security

- Run `bash scripts/healthcheck.sh http://localhost $API_KEY` after every deploy
- Review [SECURITY.md](SECURITY.md) before production release
- Rotate `API_KEY` and `JWT_SECRET_KEY` every 90 days
- Use a secrets manager (HashiCorp Vault, AWS Secrets Manager) for production secrets
- Enable audit logging for all API access
- Monitor failed authentication attempts via `/api/v1/audit?severity=critical`
