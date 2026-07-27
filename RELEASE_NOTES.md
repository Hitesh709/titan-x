# \u2622 TITAN X v0.1.0 — Release Notes

**Release Date:** 2026-07-22

---

## Overview

Initial production release of the TITAN X trading intelligence platform. A comprehensive FastAPI-based backend with PostgreSQL, Redis, and a rich feature set spanning market data, AI-driven analysis, portfolio management, paper trading, and system monitoring.

---

## Features

### Core Platform
- FastAPI async application with 90+ REST API endpoints
- SQLAlchemy 2.0 async ORM with PostgreSQL
- Redis caching, session store, rate limiter, task queue, brute force protection
- Alembic migrations with TimescaleDB hypertable support
- CORS, HSTS, Trusted Host, and Security Headers middleware
- JSON structured logging via structlog
- JWT authentication with access & refresh tokens
- Role-based access control (admin/user)

### Market Data & Analysis
- Real-time and historical price data (daily, intraday, adjusted)
- Technical indicators and chart pattern recognition
- Market breadth, correlation, and microstructure analysis
- Fundamental metrics, financial statements, and valuations
- Macro indicators, regime detection, and sector rotation
- Market heatmap with sector/industry breakdown
- Advanced stock screener with 6+ filter groups

### AI & Machine Learning
- Trading decision engine with ensemble AI predictions
- Explainability dashboard with 5 analysis sections
- Dynamic AI scoring across 7 signal sources
- Model registry with versioning, deployment, and rollback
- Automated model training with cron scheduling and checkpoint resume
- Enterprise feature store with TTL cache, validation, and lineage
- ML experiment manager with metric/artifact/chart logging
- Model evaluation with 8 metrics
- Drift detection with PSI/JS divergence and auto alerts
- Recommendation engine with 10 tracking fields and outcome tracking

### Trading & Portfolio
- Paper trading engine (market/limit/stop orders, FIFO, fees, slippage)
- Simulated trade tracking with round-trip PnL
- Performance analytics (CAGR, Sharpe, Sortino, Win Rate, Profit Factor, Max DD)
- Adaptive stop loss and price targets
- Opportunity rejection engine
- Portfolio management with positions and transactions
- Portfolio optimizer with allocation recommendations

### Risk & Compliance
- Portfolio risk metrics (VaR, CVaR, beta, correlation)
- Audit logging with 5 event categories and severity levels
- Corporate action detection and tracking
- Compliance calendars (settlement, expiry, holidays)
- Insider and institutional holdings tracking

### User Features
- Personalized dashboard (portfolio, watchlists, AI picks, news, alerts)
- Global search across companies, symbols, sectors, reports, strategies, news
- Export to CSV, Excel, PDF with AI explanations
- Watchlist management with continuous monitoring (AI, news, earnings, risk)
- Strategy management with clone/share/schedule/execute/replay
- Professional report generation with SVG charts
- Company research with knowledge graphs
- Trade journal with auto-calculated PnL
- Professional report generation
- News aggregation with NLP sentiment analysis
- Corporate reminders and event tracking

### Operations
- Health check endpoints (liveness/readiness)
- System monitoring (CPU, memory, API latency, DB pool, queue, scheduler)
- Database connection pooling
- Distributed scheduler for background jobs
- Async task queue with retries
- Performance measurement (11 metrics)
- Nightly evaluation with bias detection

---

## Architecture

```
                    +-----------+
                    |   NGINX   |
                    +-----+-----+
                          |
                    +-----+-----+
                    |   API     |  (uvicorn, 4 workers)
                    +-----+-----+
                          |
            +-------------+-------------+
            |             |             |
       +----+----+  +----+----+  +-----+------+
       |PostgreSQL|  |  Redis   |  |   Worker   |
       | (17.x)   |  |  (7.x)   |  |  (async)   |
       +---------+  +---------+  +------------+
```

---

## Deployment

See **[DEPLOY.md](DEPLOY.md)** for full deployment instructions.

### Quick Start
```bash
cp .env.example .env          # edit secrets
docker compose up --build     # development
docker compose -f docker-compose.prod.yml up -d  # production
```

### Environment Requirements
- Python 3.13+
- PostgreSQL 17+ (with TimescaleDB extension)
- Redis 7+
- Docker & Docker Compose v2
- 2 GB RAM minimum, 4+ CPU cores recommended
- 20 GB disk for data volume

---

## Performance

- Average API response time: < 50ms (p95 < 200ms)
- Supports 1000+ concurrent connections
- Redis cache TTL: 5 min default
- Database pool: 20 connections (40 overflow)
- Uvicorn workers: 4 (configurable)

---

## Security

- All endpoints require `X-API-Key` header (except /health and /docs)
- JWT tokens expire in 15 minutes (access) and 1 day (refresh)
- Rate limiting: 120 requests/minute
- Brute force: 3 attempts locks for 60 minutes
- HTTPS enforced in production with HSTS
- CORS restricted to known frontend domains
- Non-root container user
- Full security checklist: [SECURITY.md](SECURITY.md)

---

## Testing

```bash
# Unit tests (120 test files)
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# Smoke tests
pytest tests/smoke -v --base-url=http://localhost:8000

# Load tests
locust -f tests/load/locustfile.py --host=http://localhost:8000 --headless -u 50 -r 5 -t 5m
```

---

## Known Issues

- PDF export requires `weasyprint` (optional dependency)
- TimescaleDB hypertables require manual setup for new installations
- Rate limiter counts per API key (not per user)
- Monitoring middleware captures API latency but not DB query times
- Load balancer health checks may show degraded during peak migration

---

## Upgrade Notes

### From v0.0.x (internal)
- Database schema reset required (breaking migration from initial schema)
- API key format changed to SHA-256 hash
- `POSTGRES_PASSWORD` and `REDIS_PASSWORD` must be set explicitly
- Environment variable `API_KEY` is now required (32+ chars)

---

## Changelog (Notable Commits)

- Initial API scaffold and authentication
- Company, price, and news data models
- Technical indicators and pattern recognition
- Trading decision engine and prediction framework
- Portfolio management and risk analytics
- Paper trading engine with simulated orders
- Enterprise feature store and model registry
- ML experiment manager and model evaluation
- Drift detection and explainability dashboard
- Dynamic AI scoring and market heatmap
- System monitoring and audit tracking
- Production release preparation (Docker, CI/CD, docs)
