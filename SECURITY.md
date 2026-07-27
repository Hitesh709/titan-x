# Security Checklist — TITAN X Production Release

## Authentication & Authorization

- [ ] JWT secret key is 64+ random characters, rotated every 90 days
- [ ] API key is 32+ random characters, rotated on compromise
- [ ] `X-API-Key` required on all external API endpoints (except health/docs)
- [ ] `ACCESS_TOKEN_EXPIRE_MINUTES` set to 15 or lower
- [ ] `REFRESH_TOKEN_EXPIRE_DAYS` set to 1 or lower
- [ ] Password hashing uses bcrypt (passlib)
- [ ] Brute force protection enabled (3 attempts / 15 min window / 60 min block)
- [ ] Rate limiting enabled (120 req/min)
- [ ] RBAC enforced on admin/sensitive endpoints

## Transport Security

- [ ] HTTPS enforced (ENABLE_HTTPS_REDIRECT=true)
- [ ] TLS 1.2+ only (no SSLv3, TLSv1.0, TLSv1.1)
- [ ] HSTS enabled (max-age=31536000, includeSubDomains, preload)
- [ ] Valid TLS certificate from trusted CA (not self-signed in prod)
- [ ] `TRUSTED_HOSTS` restricts valid Host headers

## API Security

- [ ] CORS origins restricted to known frontend domains
- [ ] All user input validated via Pydantic schemas
- [ ] SQL injection prevented via SQLAlchemy parameterized queries
- [ ] No sensitive data in URL parameters (use POST body)
- [ ] API docs disabled in production (DOCS_ENABLED=false)
- [ ] Request ID header set on all responses for tracing
- [ ] `X-Content-Type-Options: nosniff` enforced
- [ ] `X-Frame-Options: DENY` enforced
- [ ] `X-XSS-Protection: 1; mode=block` enforced
- [ ] `Referrer-Policy: strict-origin-when-cross-origin` enforced
- [ ] `Permissions-Policy` restricts camera/mic/geolocation

## Data Security

- [ ] Database connection string uses strong password (not default)
- [ ] Redis connection uses strong password (not default)
- [ ] `SQL_ECHO=false` in production (no query logging)
- [ ] `DEBUG=false` in production (no stack traces)
- [ ] Secrets never logged or exposed in error messages
- [ ] Audit logging enabled for all API calls
- [ ] Email notifications for security events (login from new IP, password change)
- [ ] Data encryption at rest (disk-level)

## Infrastructure Security

- [ ] Docker containers run as non-root user (titan)
- [ ] No security-essential env vars in docker-compose.yml (use .env)
- [ ] `.env` files in `.gitignore`
- [ ] Docker images scanned for vulnerabilities
- [ ] Container resource limits set (CPU/Memory)
- [ ] Logs rotated and retained for 30+ days
- [ ] Monitoring alerts on 5xx error spikes (>1% in 5min)
- [ ] Monitoring alerts on P95 latency > 1s

## Dependency Security

- [ ] All Python dependencies pinned to exact versions
- [ ] `safety check` or `pip audit` run in CI
- [ ] Regular `pip-audit` schedule (weekly)
- [ ] Dependencies updated quarterly at minimum
- [ ] No deprecated or unmaintained packages

## Incident Response

- [ ] Rollback script tested and documented
- [ ] Health check endpoints monitored (Prometheus/AlertManager)
- [ ] Slack/PagerDuty notification on deploy
- [ ] On-call rotation defined
- [ ] Post-mortem template exists

## Pre-Release Verification

- [ ] All unit tests pass (`pytest tests/unit -v`)
- [ ] All integration tests pass (`pytest tests/integration -v`)
- [ ] All smoke tests pass (`pytest tests/smoke -v --base-url=<staging>`)
- [ ] Load test completed with <1% error rate at 2x expected traffic
- [ ] Ruff linter passes (`ruff check src tests`)
- [ ] Bandit security scan passes (`bandit -r src`)
- [ ] No secrets committed to repository
- [ ] Staging deployment validated before production
