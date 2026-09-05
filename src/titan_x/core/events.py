import asyncio
from pathlib import Path

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from titan_x.core.config import Settings
from titan_x.db.base import Base
from titan_x.db.session import create_engine, create_session_factory
from titan_x.infrastructure.cache import MemoryCache, RedisCache
from titan_x.infrastructure.memory_session_store import MemorySessionStore
from titan_x.infrastructure.scheduler import Scheduler
from titan_x.infrastructure.session_store import RedisSessionStore
from titan_x.infrastructure.task_queue import TaskQueue, Worker
from titan_x.jobs import cleanup_expired_tokens, database_health_check, market_close, market_data_ingestion, market_open, process_delayed_trades, prune_old_executions
from titan_x.models import *  # noqa: F401,F403

logger = structlog.get_logger(__name__)


async def _sync_missing_columns(engine: AsyncEngine) -> None:
    from sqlalchemy import inspect as sa_inspect

    changed = 0
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = await conn.run_sync(
                lambda sync_conn, t=table: {
                    c["name"] for c in sa_inspect(sync_conn).get_columns(t.name)
                }
            )
            for col in table.columns:
                if col.name in existing or col.primary_key:
                    continue
                col_type = col.type.compile(dialect=conn.dialect)
                await conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}')
                )
                changed += 1
                logger.info(
                    "schema_added_column",
                    table=table.name,
                    column=col.name,
                    type=col_type,
                )
    logger.info("schema_sync_complete", columns_added=changed)


async def _ensure_sqlite_parent(settings: Settings) -> None:
    url = settings.resolved_database_url
    if not url.startswith("sqlite"):
        return
    raw_path = url.split("///", 1)[-1].split("?", 1)[0]
    if raw_path.startswith("/"):
        db_path = Path(raw_path)
    else:
        db_path = Path.cwd() / raw_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("sqlite_database_path_ready", path=str(db_path.parent))


async def on_startup(app: FastAPI, settings: Settings) -> None:
    await _ensure_sqlite_parent(settings)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.database_ready = asyncio.Event()
    logger.info(
        "database_backend_ready",
        backend=engine.url.get_backend_name(),
        driver=engine.url.get_driver_name(),
        persistent_required=settings.environment == "production",
    )

    async def _initialize_database() -> None:
        last_error: Exception | None = None
        for attempt in range(1, 6):
            try:
                async with engine.begin() as conn:
                    await asyncio.wait_for(conn.run_sync(Base.metadata.create_all), timeout=30)
                await asyncio.wait_for(_sync_missing_columns(engine), timeout=30)
                logger.info("database_tables_ready", attempt=attempt)

                if settings.ensure_demo_user_on_startup:
                    from titan_x.core.demo_user import ensure_demo_user

                    created = await asyncio.wait_for(
                        ensure_demo_user(session_factory), timeout=30
                    )
                    logger.info("demo_user_bootstrap_complete", created=created)

                if settings.seed_demo_on_startup:
                    from titan_x.core.seed_demo import seed_all

                    await asyncio.wait_for(seed_all(session_factory), timeout=60)
                    logger.info("demo_seeded_on_startup")
                app.state.database_ready.set()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                logger.exception(
                    "database_initialization_attempt_failed",
                    attempt=attempt,
                    max_attempts=5,
                )
                if attempt < 5:
                    await asyncio.sleep(3 * attempt)
        logger.error("database_initialization_failed_after_retries", attempts=5)
        raise last_error if last_error is not None else RuntimeError("Database initialization failed")

    app.state.database_init_task = asyncio.create_task(_initialize_database())
    await app.state.database_init_task

    try:
        from titan_x.services.recommendation_scan_service import run_universe_load, run_background_scan

        async def _run_recommendation_scan(sf) -> None:
            await app.state.database_ready.wait()
            try:
                universe = await run_universe_load(sf)
                logger.info("recommendation_universe_ready", **universe)
                result = await run_background_scan(sf, max_age_minutes=0, limit=None)
                logger.info("recommendation_scan_startup_complete", **result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("recommendation_scan_startup_failed")

        async def _ingest_market_data_later(sf) -> None:
            await app.state.database_ready.wait()
            if not settings.market_data_ingest_on_startup:
                logger.info("market_data_ingest_skipped")
                return
            try:
                from titan_x.services.market_data_service import run_market_data_ingestion

                result = await run_market_data_ingestion(
                    sf, max_symbols=settings.market_data_ingest_max_symbols
                )
                logger.info(
                    "market_data_ingest_startup",
                    provider=result.get("provider"),
                    requested=result.get("symbols_requested"),
                    ok=result.get("symbols_ok"),
                    failed=result.get("symbols_failed"),
                    inserted=result.get("inserted_total"),
                )
                for error in result.get("errors") or []:
                    logger.error(
                        "market_data_symbol_failed",
                        symbol=error.get("symbol"),
                        provider=error.get("provider"),
                        error=error.get("error"),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("market_data_ingest_run_failed")

        async def _ingest_news_later(sf) -> None:
            await app.state.database_ready.wait()
            try:
                from titan_x.services.news_feed import run_news_ingestion

                result = await run_news_ingestion(sf)
                logger.info(
                    "news_ingest_startup",
                    fetched=result.get("fetched"),
                    created=result.get("created"),
                )
            except Exception:
                logger.exception("news_ingest_startup_failed")

        async def _universe_load_later() -> None:
            await app.state.database_ready.wait()
            try:
                result = await run_universe_load(session_factory)
                logger.info("nse_universe_startup", **result)
            except Exception:
                logger.exception("nse_universe_startup_failed")
                return
            # Run the startup writers sequentially. SQLite supports one writer
            # at a time; this avoids recommendation/news ingestion locking the
            # persistent trading database during deployment.
            await _ingest_market_data_later(session_factory)
            await _ingest_news_later(session_factory)
            await _run_recommendation_scan(session_factory)

        asyncio.create_task(_universe_load_later())
    except Exception:
        logger.exception("nse_universe_startup_failed")

    redis: Redis | None = None
    try:
        redis = Redis.from_url(
            str(settings.redis_url), encoding="utf-8", decode_responses=True
        )
        await asyncio.wait_for(redis.ping(), timeout=5)
        logger.info("redis_connected")
    except Exception as exc:
        logger.warning(
            "redis_unavailable_using_safe_fallback",
            error_type=type(exc).__name__,
            message=str(exc),
        )
        redis = None
    app.state.redis = redis

    if redis is not None:
        app.state.cache = RedisCache(redis)
        app.state.session_store = RedisSessionStore(redis)
    else:
        app.state.cache = MemoryCache()
        app.state.session_store = MemorySessionStore()

    app.state.task_queue = TaskQueue(redis) if redis is not None else None
    if app.state.task_queue is not None and settings.task_queue_enabled:
        app.state.worker = Worker(app.state.task_queue, settings)
        await app.state.worker.start()
        logger.info("task_queue_initialized")
    else:
        app.state.worker = None

    app.state.scheduler = Scheduler(app.state.task_queue, settings) if app.state.task_queue is not None else None
    if app.state.scheduler is not None and settings.scheduler_enabled:
        await app.state.scheduler.start()
        logger.info("scheduler_started")

    app.state.startup_tasks = []
