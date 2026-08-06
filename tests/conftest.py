import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Allow any host during tests (TrustedHostMiddleware)
os.environ.setdefault("TRUSTED_HOSTS", "*")
# Required settings for modules that instantiate Settings()/get_settings() at
# import time (e.g. titan_x.main) before fixtures can inject test values.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("API_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "b" * 32)

import titan_x.models  # noqa: F401 — register all models with Base.metadata
from titan_x.api.dependencies import require_api_key
from titan_x.core.config import Settings, get_settings
from titan_x.db.base import Base
from titan_x.db.repository import BaseRepository
from titan_x.models.user import User

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///",
        redis_url="redis://localhost:6379/0",
        api_key="a" * 32,
        jwt_secret_key="b" * 32,
        docs_enabled=False,
        environment="test",
        trusted_hosts="localhost,127.0.0.1,test,testserver",
    )


@pytest_asyncio.fixture
async def in_memory_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    from sqlalchemy import event as sa_event

    engine = create_async_engine(str(settings.database_url))

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(in_memory_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(in_memory_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def mock_redis() -> AsyncMock:

    async def _true(*args, **kwargs):
        return True

    async def _zero(*args, **kwargs):
        return 0

    async def _none(*args, **kwargs):
        return None

    redis = AsyncMock(spec=Redis)
    redis.ping.return_value = True
    redis.exists.side_effect = _zero
    redis.get.side_effect = _none
    redis.setex.side_effect = _true
    redis.delete.side_effect = _true
    redis.incr.side_effect = _zero
    redis.expire.side_effect = _true
    async def _empty_list(*args, **kwargs):
        return []

    redis.keys.side_effect = _empty_list
    return redis


@pytest_asyncio.fixture
async def app(in_memory_engine: AsyncEngine, mock_redis: AsyncMock) -> AsyncIterator[FastAPI]:
    from titan_x.api.dependencies import get_brute_force_protector, get_rate_limiter
    from titan_x.main import app as _app

    _app.state.session_factory = async_sessionmaker(in_memory_engine, expire_on_commit=False)
    _app.state.redis = mock_redis
    _app.state.engine = in_memory_engine
    _app.dependency_overrides[require_api_key] = lambda: None

    class _NoOpProtector:
        async def is_blocked(self, *a, **kw):
            return False
        async def record_failure(self, *a, **kw):
            return 0
        async def record_failure_sorted(self, *a, **kw):
            return False
        async def reset_attempts(self, *a, **kw):
            pass
        async def close(self):
            pass

    _app.dependency_overrides[get_brute_force_protector] = lambda: _NoOpProtector()
    # Disable Redis-backed rate limiting in tests; the AsyncMock redis cannot
    # emulate a transactional pipeline used by RateLimiter.check().
    _app.dependency_overrides[get_rate_limiter] = lambda: None
    _app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite+aiosqlite:///",
        redis_url="redis://localhost:6379/0",
        api_key="a" * 32,
        jwt_secret_key="b" * 32,
        docs_enabled=False,
        environment="test",
        trusted_hosts="*",
    )
    yield _app
    _app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def user_repo(db_session: AsyncSession) -> BaseRepository[User]:
    return BaseRepository(db_session, User)


@pytest.fixture
def any_redis_url() -> str | None:
    return os.environ.get("TEST_REDIS_URL") or os.environ.get("REDIS_URL")


@pytest.fixture
def any_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
