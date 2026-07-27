import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.api.dependencies import require_api_key
from titan_x.db.base import Base

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def api_key() -> str:
    return "a" * 32


@pytest.fixture
async def integration_app(any_database_url: str | None, any_redis_url: str | None):
    """Yield the app wired to real PostgreSQL and Redis when both URLs are set."""
    if not any_database_url or not any_redis_url:
        pytest.skip("TEST_DATABASE_URL and TEST_REDIS_URL required for integration tests")

    from titan_x.main import app as _app

    engine = create_async_engine(any_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from redis.asyncio import Redis

    redis = Redis.from_url(any_redis_url, encoding="utf-8", decode_responses=True)
    _app.state.engine = engine
    _app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    _app.state.redis = redis
    _app.dependency_overrides[require_api_key] = lambda: None

    yield _app

    _app.dependency_overrides.clear()
    await redis.aclose()
    await engine.dispose()


@pytest.mark.skip(reason="Requires live PostgreSQL and Redis — manage via CI only")
async def test_liveness(integration_app) -> None:
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


@pytest.mark.skip(reason="Requires live PostgreSQL and Redis — manage via CI only")
async def test_readiness_returns_200_when_everything_healthy(integration_app) -> None:
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload == {
        "status": "ready",
        "database": "available",
        "redis": "available",
    }
