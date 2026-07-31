# TITAN X Deployment Guide

The platform is split into two Render Web Services:

| Service     | Purpose                        | URL                          |
|-------------|--------------------------------|------------------------------|
| `titan-x`   | FastAPI backend (Python)       | https://titan-x.onrender.com |
| `titan-x-web`| Next.js frontend (Node)        | https://titan-x-web.onrender.com |

Both deploy automatically from the `main` branch of `github.com/Hitesh709/titan-x`.

## 1. Backend (`titan-x`)

Already live. Requires the following environment variables (set in the Render dashboard):

```
ENVIRONMENT=production
DATABASE_URL=sqlite+aiosqlite:///./titan_x_prod.db
REDIS_URL=redis://localhost:6379/0
API_KEY=titan-x-prod-api-key-2026-abcdef
JWT_SECRET_KEY=<32+ chars>
TRUSTED_HOSTS=*
DOCS_ENABLED=true
LOG_LEVEL=INFO
ENABLE_HTTPS_REDIRECT=true
CORS_ORIGINS=https://titan-x-web.onrender.com,http://localhost:3000
SEED_DEMO_ON_STARTUP=true  # optional; seeds demo data on first startup
```

Notes:
- `CORS_ORIGINS` is a comma-separated list of allowed browser origins. It **must** include the frontend origin or browser requests will be rejected. Wildcards (`*`) are disallowed.
- The DB tables are created automatically on startup (`Base.metadata.create_all` in `on_startup`), so no separate migration step is required.
- Redis is optional. If unavailable, the app falls back to in-memory/no-op stubs and auth still works (rate-limiting/brute-force protection is skipped).
- **Demo data**: set `SEED_DEMO_ON_STARTUP=true` to populate the DB on startup with 26 companies, ~260 days of prices, sector performance, market breadth, plus a demo user `demo@titanx.app` / `Demo1234!` with a paper account, watchlists, AI scores, news and alerts. The seed is idempotent (re-running replaces the seeded rows) and runs after table creation. Run it standalone with `python scripts/seed_demo.py`. Unset the variable after the first successful deploy to stop re-seeding on every restart.

## 2. Frontend (`titan-x-web`)

The repo contains `render.yaml` describing the service. To create it:

1. In the Render dashboard: **New + → Blueprint**
2. Select the `Hitesh709/titan-x` repository
3. Render provisions the `titan-x-web` service (root dir `web`)

Or create it manually:

1. **New + → Web Service** → select the repo
2. **Root Directory**: `web`
3. **Runtime**: Node
4. **Build Command**: `npm ci && npm run build`
5. **Start Command**: `npm start`
6. Environment variables:
   - `NEXT_PUBLIC_API_URL=https://titan-x.onrender.com/api/v1` (build-time, must be set before the first build)
   - `NODE_ENV=production`
7. Deploy. The first build takes a few minutes.

## 3. Verification

1. Open `https://titan-x-web.onrender.com` → landing page loads.
2. Click **Get Started** → register a new account (email + password ≥ 8 chars).
3. You are redirected to `/dashboard`; sidebar shows your email in the bottom-left.
4. In the browser DevTools console, the `/api/v1/auth/login` and `/api/v1/auth/me` calls should return 200 with `Authorization: Bearer <token>`.

## Common failures

- **Login 401 "Invalid API key"** — the JWT must be sent as `Authorization: Bearer <token>` (see `web/lib/api.ts`), not as `X-API-Key` (which is reserved for the static API key).
- **Register returns 409** — the email already exists; register with a new email.
- **CORS errors in the browser console** — `CORS_ORIGINS` on the backend does not include the frontend origin, or the backend hasn't been redeployed after the change.
- **Login 500** — usually an old backend build before the startup table-creation fix; redeploy the backend (push a commit or click Deploy on the service).
- **Stale frontend** — `NEXT_PUBLIC_API_URL` is inlined at build time; change it, rebuild, and redeploy.

## Local development

Backend:
```
pip install -r requirements.txt
uvicorn titan_x.main:app --reload --port 8000
```

Frontend (in `web/`):
```
npm install
npm run dev
```
Set `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` in `web/.env.local` and include `http://localhost:3000` in the backend `CORS_ORIGINS`.
