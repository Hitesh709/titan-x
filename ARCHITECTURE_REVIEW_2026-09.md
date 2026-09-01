# Xecaps / TITAN X — Architecture Review

**Review date:** 2026-09-01  
**Repository:** `Hitesh709/titan-x`  
**Review branch:** `codex/architecture-hardening-2026-09`

## Executive assessment

The repository already contains a substantial production-oriented platform rather than a blank MVP. The backend is a large async FastAPI application with SQLAlchemy, PostgreSQL/TimescaleDB migrations, Redis, background workers, schedulers, security middleware, audit logging, and a Next.js web application. The repository architecture document reports ~67k lines across ~318 Python files and 92 API routers, with 60+ business services.

The strongest architectural decision is the separation of API routers, services, models, schemas, database infrastructure, and workers. The most important remaining work is to make the financial intelligence layer more scientifically auditable: point-in-time data, provenance, model/version snapshots, prediction outcome tracking, and properly calibrated probabilities.

## What was verified

- FastAPI application entry point and middleware stack.
- Pydantic settings and environment-driven configuration.
- Authentication, refresh-token rotation, MFA and brute-force controls.
- PostgreSQL/Redis architecture and Alembic migration chain.
- Next.js frontend structure and production build configuration.
- AI recommendation engine and its six analytical pillars.
- Render blueprint and frontend/backend separation.
- GitHub Actions CI/CD configuration.

## Strengths

### Platform

- Async FastAPI + SQLAlchemy 2 architecture is appropriate for an API-heavy platform.
- Repository/service/schema separation is already established.
- Alembic migrations are present and sequential.
- Redis is used for caching, rate limiting, brute-force protection and locks.
- Structured logging, request IDs and security-event auditing are present.
- Docker and Render deployment definitions exist.
- The web application is a Next.js application, not a simple static React page.

### Security

- JWT access/refresh tokens are implemented.
- Refresh-token records are persisted and revocable.
- MFA and recovery codes exist.
- Brute-force and rate-limit controls exist.
- Trusted-host, HTTPS redirect, security headers and request-size middleware exist.
- Wildcard CORS is explicitly rejected by configuration.

### AI

- The recommendation engine is deterministic and unit-testable.
- It has multiple analytical pillars rather than one opaque score.
- It has explicit NO-TRADE gates.
- It records evidence, caution, model agreement, risk/reward and historical-pattern statistics.
- The holding period is bounded to a 15-day default, consistent with the project's short-term objective and below the 30-day maximum.

## Important findings

### 1. AI probability must not be presented as statistically calibrated yet

The recommendation engine currently derives its probability using a sigmoid transformation of the ensemble score and then applies agreement/data-quality multipliers. That is an **estimated model probability**, not a statistically calibrated probability unless it has been fitted and validated against out-of-sample outcomes.

**Action:** preserve the API field for compatibility, but introduce an explicit probability methodology/version and later add Platt scaling, isotonic calibration, or another validated calibration layer using strictly out-of-sample data.

### 2. Point-in-time backtesting is mandatory

A financial model can look highly accurate if it accidentally sees information that was unavailable at the prediction timestamp. Xecaps should enforce an immutable historical clock for every backtest.

**Required architecture:**

`raw data -> validated data -> point-in-time snapshot -> features -> model -> prediction -> outcome`

### 3. Data provenance should be first-class

Every material market/news/fundamental input should retain source, source timestamp, ingestion timestamp, symbol/instrument identity, quality status and revision/version metadata.

This is necessary to answer: **"Why did Xecaps make this decision at that time?"**

### 4. Prediction records should be immutable

Each prediction should capture model version, feature version, market regime, data snapshot, score, probability, target, stop, horizon and eventual outcome. This enables honest live performance measurement and model governance.

### 5. Authentication storage is a hardening opportunity

The web client currently stores access and refresh tokens in browser localStorage. This is convenient but increases exposure if an XSS vulnerability occurs. A future security hardening pass should move the refresh credential to a Secure/HttpOnly/SameSite cookie and keep the access token short-lived.

This is deliberately not changed in this architecture pass because it requires coordinated backend/frontend contract changes and a migration strategy.

### 6. Refresh-token rotation should be concurrency-safe

The refresh flow checks a token record and then revokes it. Concurrent requests can race unless the token row is locked transactionally. The production implementation should use a database row lock/atomic state transition so a refresh token can be consumed exactly once.

### 7. The service layer is large

The repository already documents several large service modules. The largest remaining candidates include explainability, professional reporting and pattern recognition. These should be split only along stable domain boundaries; avoid a premature microservice explosion.

### 8. CI previously did not validate the frontend

The original CI validated backend lint/tests/build and security reports, but did not run the Next.js typecheck/build. The hardening branch now adds a dedicated frontend job and makes the production Docker build depend on it.

### 9. Security scanning should gate releases

The previous Bandit/Safety configuration used non-blocking behavior. The hardening branch changes this to failing security checks and uses `pip-audit` for dependency vulnerability detection.

## Target architecture

```text
                         XECAPS
                           |
                  Web / Mobile Clients
                           |
                     API / Identity
                           |
                    Domain Services
                           |
                     Event / Job Bus
                           |
       +-------------------+-------------------+
       |                   |                   |
  Data Intelligence   AI Intelligence    Risk Intelligence
       |                   |                   |
  ingestion            features           exposure
  validation           model registry     stress tests
  provenance            inference          limits
  point-in-time        calibration        portfolio risk
       |                   |                   |
       +-------------------+-------------------+
                           |
                    Decision Engine
                           |
                 Auditable Prediction
                           |
             evidence + uncertainty + risk
                           |
                 user / alert / API
```

## Recommended implementation order

1. Finish CI hardening and verify it on the branch.
2. Make refresh-token rotation transactionally safe.
3. Add prediction/audit snapshots and explicit model/feature versions.
4. Add data provenance and freshness gates.
5. Implement point-in-time backtesting.
6. Add real probability calibration and calibration reports.
7. Add live prediction outcome tracking at 1/3/5/10/15/20/30 days.
8. Only then expand the AI ensemble and options/derivatives intelligence.

## Quality gates

A production recommendation should be allowed only when:

- required market data is present and fresh;
- the input snapshot is reproducible;
- no future information is used;
- the model version is known;
- the feature version is known;
- risk/reward constraints pass;
- the recommendation is explainable;
- probability methodology is known;
- the prediction is persisted for later outcome evaluation.

## Product principle

Xecaps should never promise a "99% sure-shot" result. The architecture should instead make accuracy measurable and falsifiable. Every signal should eventually be evaluated against its real 30-day outcome, with performance broken down by model, regime, sector, liquidity and confidence bucket.

That evidence-driven feedback loop is the foundation for turning Xecaps into a serious financial intelligence platform.
