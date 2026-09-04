import asyncio

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


async def on_startup(app: FastAPI, settings: Settings) -> None:
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
        try:
            async with engine.begin() as conn:
                await asyncio.wait_for(conn.run_sync(Base.metadata.create_all), timeout=30)
            await asyncio.wait_for(_sync_missing_columns(engine), timeout=30)
            logger.info("database_tables_ready")

            if settings.seed_demo_on_startup:
                from titan_x.core.seed_demo import seed_all

                await asyncio.wait_for(seed_all(session_factory), timeout=60)
                logger.info("demo_seeded_on_startup")
            app.state.database_ready.set()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("database_initialization_failed")

    app.state.database_init_task = asyncio.create_task(_initialize_database())

    # Database-backed background services must not start before the SQLite
    # schema exists. This prevents the scheduler/worker race where they query
    # the jobs table while database initialization is still in progress.
    await app.state.database_init_task

    try:
        from titan_x.services.recommendation_scan_service import run_universe_load

        async def _ingest_market_data_later(sf) -> None:
            await app.state.database_ready.wait()
            if not settings.market_data_ingest_on_startup:
                logger.info("market_data_ingest_skipped")
                return
            try:
                from titan_x.services.market_data_service import run_market_data_ingestion

                async def _run() -> None:
                    try:
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
                    except Exception:
                        logger.exception("market_data_ingest_run_failed")

                asyncio.create_task(_run())
            except Exception:
                logger.exception("market_data_ingest_startup_failed")

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
            await _ingest_market_data_later(session_factory)
            await _ingest_news_later(session_factory)

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
        app.state.session_store = RedisSessionStore(
            redis, default_ttl=settings.session_ttl
        )
        logger.info("redis_cache_and_sessions_ready")
    else:
        app.state.cache = MemoryCache()
        app.state.session_store = MemorySessionStore(default_ttl=settings.session_ttl)
        logger.warning(
            "redis_fallback_active",
            cache="memory",
            sessions="memory",
            note="Configure REDIS_URL for shared production cache and sessions",
        )

    if settings.task_queue_enabled and redis is not None:
        app.state.task_queue = TaskQueue(redis)
        app.state.background_worker = None
        logger.info("task_queue_initialized")
    else:
        app.state.task_queue = None

    if settings.scheduler_enabled and redis is not None and app.state.database_ready.is_set():
        scheduler = Scheduler(
            redis=redis,
            task_queue=app.state.task_queue,
            session_factory=session_factory,
            poll_interval=settings.scheduler_poll_interval,
        )
        scheduler.register_job("daily:cleanup_tokens", cleanup_expired_tokens)
        scheduler.register_job("daily:health_check", database_health_check)
        scheduler.register_job("daily:prune_executions", prune_old_executions)
        scheduler.register_job("market:open", market_open)
        scheduler.register_job("market:close", market_close)
        scheduler.register_job("market:data_ingestion", market_data_ingestion)
        scheduler.register_job("market:process_trades", process_delayed_trades)
        app.state.scheduler = scheduler
        asyncio.create_task(scheduler.start())
        logger.info("scheduler_initialized")
        if settings.run_worker_in_process and app.state.task_queue is not None:

            async def _handle_task(task: dict) -> None:
                job_type = task.get("type")
                job = scheduler._registered_jobs.get(job_type)
                if job is None:
                    logger.warning("worker_no_handler", job_type=job_type)
                    return
                payload = dict(task.get("payload") or {})
                async with session_factory() as session:
                    payload["session"] = session
                    try:
                        result = await job.execute(payload)
                    except Exception:
                        logger.exception("worker_task_failed", job_type=job_type)
                        result = {"status": "failed", "error": "unhandled exception"}
                job_id = payload.get("job_id")
                if job_id is not None:
                    await scheduler.handle_completion(
                        job_id,
                        result.get("status", "failed"),
                        result.get("duration_ms"),
                        result.get("error"),
                    )

            worker = Worker(
                app.state.task_queue,
                "scheduled_jobs",
                _handle_task,
                poll_interval=settings.task_queue_poll_interval,
                max_retries=settings.task_queue_max_retries,
            )
            app.state.background_worker = worker
            asyncio.create_task(worker.start())
            logger.info("in_process_worker_started")
    else:
        app.state.scheduler = None

    if settings.backup_enabled:
        from titan_x.infrastructure.backup import backup_loop

        asyncio.create_task(backup_loop(settings))
        logger.info(
            "backup_loop_started", interval_hours=settings.backup_interval_hours
        )


async def on_shutdown(app: FastAPI, settings: Settings) -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        await scheduler.stop()
    worker = getattr(app.state, "background_worker", None)
    if worker is not None:
        await worker.stop()
    cache = getattr(app.state, "cache", None)
    if cache is not None:
        await cache.close()
    session_store = getattr(app.state, "session_store", None)
    if session_store is not None:
        await session_store.close()
    redis: Redis | None = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()
    database_init_task = getattr(app.state, "database_init_task", None)
    if database_init_task is not None and not database_init_task.done():
        database_init_task.cancel()
        try:
            await database_init_task
        except asyncio.CancelledError:
            pass
    engine: AsyncEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
    logger.info("application_stopped")
