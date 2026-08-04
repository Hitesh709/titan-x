import asyncio
import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from titan_x.core.config import Settings
from titan_x.db.session import create_engine, create_session_factory
from titan_x.infrastructure.cache import RedisCache
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
from titan_x.db.base import Base
from titan_x.models import *  # noqa: F401, F403 - register all models

logger = structlog.get_logger(__name__)


async def on_startup(app: FastAPI, settings: Settings) -> None:
    engine: AsyncEngine = create_engine(settings)
    session_factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_ready")

    if settings.seed_demo_on_startup:
        from titan_x.core.seed_demo import seed_all

        await seed_all(session_factory)
        logger.info("demo_seeded_on_startup")

    try:
        from titan_x.services.recommendation_scan_service import run_universe_load

        result = await run_universe_load(session_factory)
        logger.info("nse_universe_startup", **result)
    except Exception:  # noqa: BLE001
        logger.exception("nse_universe_startup_failed")

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
        cache = AsyncMock()
        session_store = AsyncMock()
    app.state.cache = cache
    app.state.session_store = session_store

    if settings.task_queue_enabled and redis is not None:
        task_queue = TaskQueue(redis)
        app.state.task_queue = task_queue
        app.state.background_worker = None
        logger.info("task_queue_initialized")
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
        logger.info("scheduler_initialized")
    else:
        app.state.scheduler = None


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
