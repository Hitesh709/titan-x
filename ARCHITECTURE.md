# TitanX Backend Architecture

Enterprise review record for the FastAPI backend. Covers the current
architecture, the refactors applied during this review, test-suite status,
verification workflow, and known technical debt.

## 1. System overview

- **Stack**: FastAPI (async) · SQLAlchemy 2.0 async ORM · Postgres (prod) /
  SQLite+aiosqlite (tests) · Redis (cache/rate-limit/brute-force/locks) ·
  structlog · pydantic-settings.
- **Codebase**: `src/titan_x/` — 318 Python files, ~67,460 lines.
- **Frontend**: Next.js app in `web/` (TypeScript, `npm run build` +
  `npx tsc --noEmit` for verification).

## 2. Layout

```
src/titan_x/
  api/            FastAPI routers (92 routers in api/v1/) + dependencies
  core/           config (Settings), security, exceptions, time, middleware,
                  seed_demo
  db/             engine/session factory, Base, repository (BaseRepository)
  infrastructure/ redis clients, rate_limiter, brute_force, scheduler,
                  task_queue, market data providers
  models/         SQLAlchemy models
  services/       60+ business services
  schemas/        Pydantic request/response models
  workers/        background jobs
```

## 3. Configuration

`titan_x.core.config.Settings` is a pydantic-settings `BaseSettings` read from
the environment / `.env`. It is instantiated at import time in `main.py`, so
these are required before the app starts:

- `DATABASE_URL`
- `REDIS_URL`
- `API_KEY`
- `JWT_SECRET_KEY`

`tests/conftest.py` sets `os.environ.setdefault(...)` for these so the test
suite imports without a `.env`.

## 4. Request lifecycle / error handling

`main.py` installs, in order:

1. `TrustedHostMiddleware` (`trusted_hosts` from Settings)
2. `HTTPSRedirectMiddleware` (non-test environments)
3. Custom security-headers / request-logging middleware (existing)
4. `register_exception_handlers(app)` from `core/exceptions.py`:

   | Exception                | Status | Response body                     |
   |--------------------------|--------|-----------------------------------|
   | `RequestValidationError` | 422    | `{"detail": errors}`              |
   | `HTTPException`          | as-is  | `{"detail": ...}`                 |
   | `SQLAlchemyError`        | 500    | generic `{"detail": ...}`         |
   | `Exception`              | 500    | generic `{"detail": ...}`         |

   Every handler logs path/method/error via structlog. The generic bodies
   avoid leaking internals; the frontend (`web/lib/api.ts`) only consumes the
   `{detail}` shape, so this is a non-breaking contract.

## 5. Refactors applied in this review

- **Time policy** (`core/time.py`): `utcnow()` (aware UTC) and
  `ensure_aware()`. Replaced naive `datetime.now()` / `datetime.utcnow()`
  across `infrastructure/market_data_providers.py`,
  `services/alert_evaluation_service.py`, `services/news_scanner_service.py`,
  `services/report_generator.py`, `services/trade_journal_service.py`, and
  `services/paper_analytics_service.py`.
- **Password hashing** (`core/security.py`): moved to direct `bcrypt`
  (`hashpw`/`gensalt`/`checkpw`) because `passlib 1.7.4` is incompatible with
  `bcrypt >= 4` (`AttributeError: module 'bcrypt' has no attribute
  '__about__'`). Output format is `$2b$`, compatible with existing passlib
  hashes; verified `verify_password` True/False roundtrip.
- **Dependency injection** (`api/dependencies.py`, 464 → ~299 lines): a
  data-driven `_SESSION_SERVICE_REGISTRY` generates 39 `get_*` factories via
  `globals()`; auth/redis/settings/composed providers stay manual. Verified all
  names consumed across routers resolve ("MISSING: none").
- **Repository dedupe** (`db/repository.py`): extracted `_apply_filters()`,
  shared by `get_multi` and `count`; `count()` now honours filters.
- **Exception handlers** (`core/exceptions.py`): added (previously absent).
- **Deprecations**: `api/v1/market_heatmap.py` `Query(..., regex=...)` →
  `pattern=...`; `core/seed_demo.py` `print()` → structlog.
- **Test harness**: `pyproject.toml` gained
  `[tool.pytest.ini_options] pythonpath = ["src"]` (required because two copies
  of the repo exist — see §7).

## 6. Test-suite status

- **Scope**: `tests/unit` — 118 files, ~900 async tests. Plus `integration`
  (8), `load` (2), `smoke` (2).
- **All 118 unit files were run individually and pass** after three fixes:
  1. `tests/conftest.py`: the `app` fixture now overrides `get_rate_limiter`
     with `None` (the `AsyncMock` Redis cannot emulate the transactional
     pipeline `RateLimiter.check()` uses; previously `login` blew up with
     `TypeError: '<=' not supported between MagicMock and 'int'`).
  2. `services/paper_analytics_service.py`: `_compute_cagr` clamps the
     annualization factor to `MIN_ANNUALIZATION_YEARS = 1/365.25`, fixing an
     `OverflowError` when a closed trade was held for (near-)zero time.
  3. `tests/unit/test_sector_engine.py`: `test_ranking` / `test_rotation` now
     call `compute_all_sectors(end_date, store=True)` first — these endpoints
     read persisted `SectorPerformance` rows, matching production flow.

### Known issue: full-suite hang

Running the **entire** `tests/unit` suite in one process hangs partway and
never prints a summary. Evidence:

- Hang point is **flaky** — observed at ~36%, ~49%, and ~78% across runs.
- Every file passes individually and in small groups; nothing fails before the
  hang.
- `pytest-timeout --timeout=120 --timeout-method=thread` lets it reach ~78%
  but the process still dies mid-stream without a summary, i.e. the hang is in
  teardown/event-loop shutdown after accumulated state, not inside any single
  test.

Conclusion: a **pre-existing, flaky resource/event-loop leak** in the harness
(or an un-awaited background task), not a regression from this review. No code
change here triggers it. Workaround for verification: run the suite per-file /
in small alphabetical groups (each file completes in seconds). If needed,
`pytest-timeout` can bound the run, but it is **not** committed as a dependency.

## 7. Verification workflow ("python or node", no manual env setup)

Backend (repo-root `pyproject.toml` handles it):

```
python -m pytest tests/unit/test_<file>.py -q
```

- `pythonpath = ["src"]` makes `titan_x` importable from the repo root.
- Manual `python -c "import titan_x..."` still needs `PYTHONPATH=src` (or set
  `PYTHONPATH` to the repo's `src`) because two copies of the source tree
  exist on this machine.

Frontend:

```
cd web
npm run build        # and/or: npx tsc --noEmit
```

### Critical: two copies of the repo exist

- `C:\Users\DELL\Documents\Default Project\src` — the working copy used by the
  interactive environment and by any process without an explicit `PYTHONPATH`.
- `C:\Users\DELL\AppData\Local\Temp\opencode\clean_titanx` — the git repo and
  the authoritative source for review/commit.

The two trees **differ** (e.g. `market_heatmap.py`), so always verify against
the git repo with `pythonpath`/`PYTHONPATH` pointing at the correct `src`.

## 8. Known technical debt (pre-existing)

- **Oversized service modules** (split candidates): `market_data_collector_service.py`
  (1104L), `feature_engineering_service.py` (1103L), `datalake_service.py`
  (1045L), `explainability_engine.py` (923L), `professional_report_service.py`
  (907L), `pattern_recognition_engine.py` (845L); API router
  `api/v1/datalake.py` (936L).
- **python-jose** is pinned but deprecated and emits `datetime.utcnow()`
  warnings; long-term replace with `PyJWT`.
- `passlib` is still a pinned dependency (`passlib[bcrypt]==1.7.4`) but is no
  longer used for hashing after the direct-`bcrypt` migration; consider
  dropping it.
- No `ruff` / `typecheck` npm/poetry scripts; the repo carries ~75 pre-existing
  ruff findings (mostly `E501`, some `S110`) unrelated to this review's edits.
- `request_logging` middleware swallows auth-decode exceptions (`S110`) rather
  than logging them.
