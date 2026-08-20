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
from titan_x.infrastructure.scheduler import Scheduler
from titan_x.infrastructure.session_store import RedisSessionStore
from titan_x.infrastructure.task_queue import TaskQueue, Worker
from titan_x.jobs import (
    cleanup_expired_tokens,
    database_health_check,
    market_close,
    market_data_ingestion,
    market_open,
    process_delayed_trades,
    prune_old_executions,
)
from titan_x.models import *  # noqa: F401, F403 - register all models
from titan_x.models.loan_application import LoanApplication  # noqa: F401

logger = structlog.get_logger(__name__)


async def _sync_missing_columns(engine: AsyncEngine) -> None:
    """Create_all only creates missing tables; add missing nullable columns idempotently."""
    from sqlalchemy import inspect as sa_inspect

    changed = 0
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = await conn.run_sync(
                lambda sync_conn, t=table: {c["name"] for c in sa_inspect(sync_conn).get_columns(t.name)}
            )
            for col in table.columns:
                if col.name in existing or col.primary_key:
                    continue
                col_type = col.type.compile(dialect=conn.dialect)
                stmt = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'
                await conn.execute(text(stmt))
                changed += 1
                logger.info("schema_added_column", table=table.name, column=col.name, type=col_type)
    logger.info("schema_sync_complete", columns_added=changed)


async def on_startup(app: FastAPI, settings: Settings) -> None:
    engine: AsyncEngine = create_engine(settings)
    session_factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _sync_missing_columns(engine)
    logger.info("database_tables_ready")

    if settings.seed_demo_on_startup:
        from titan_x.core.seed_demo import seed_all
        await seed_all(session_factory)
        logger.info("demo_seeded_on_startup")

    redis: Redis | None = None
    try:
        redis = Redis.from_url(str(settings.redis_url), encoding="utf-8", decode_responses=True)
        await redis.ping()
        logger.info("redis_connected")
    except Exception:
        logger.warning("redis_unavailable - using null stubs")
        redis = None

    app.state.redis = redis

    from unittest.mock import AsyncMock
    if redis is not None:
        cache = RedisCache(redis)
        session_store = RedisSessionStore(redis, default_ttl=settings.session_ttl)
    else:
        logger.warning("redis_unavailable - falling back to in-memory cache")
        cache = MemoryCache()
        session_store = AsyncMock()
    app.state.cache = cache
    app.state.session_store = session_store

    if settings.task_queue_enabled and redis is not None:
        task_queue = TaskQueue(redis)
        app.state.task_queue = task_queue
        app.state.background_worker = None
    else:
        app.state.task_queue = None

    if settings.scheduler_enabled and redis is not None:
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
                    except Exception:  # noqa: BLE001
                        logger.exception("worker_task_failed", job_type=job_type)
                        result = {"status": "failed", "error": "unhandled exception"}
                job_id = payload.get("job_id")
                if job_id is not None:
                    await scheduler.handle_completion(job_id, result.get("status", "failed"), result.get("duration_ms"), result.get("error"))

            worker = Worker(
                app.state.task_queue,
                "scheduled_jobs",
                _handle_task,
                poll_interval=settings.task_queue_poll_interval,
                max_retries=settings.task_queue_max_retries,
            )
            app.state.background_worker = worker
            asyncio.create_task(worker.start())
    else:
        app.state.scheduler = None

    if settings.backup_enabled:
        from titan_x.infrastructure.backup import backup_loop
        asyncio.create_task(backup_loop(settings))
        logger.info("backup_loop_started", interval_hours=settings.backup_interval_hours)


async def on_shutdown(app: FastAPI, settings: Settings) -> None:
    scheduler: Scheduler | None = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        await scheduler.stop()
    worker: Worker | None = getattr(app.state, "background_worker", None)
    if worker is not None:
        await worker.stop()
    cache: RedisCache | None = getattr(app.state, "cache", None)
    if cache is not None:
        await cache.close()
    session_store: RedisSessionStore | None = getattr(app.state, "session_store", None)
    if session_store is not None:
        await session_store.close()
    redis: Redis | None = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()
    engine: AsyncEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
    logger.info("application_stopped")
