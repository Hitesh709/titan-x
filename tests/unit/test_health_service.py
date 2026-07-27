from unittest.mock import AsyncMock

import pytest

from titan_x.services.health_service import HealthService, Readiness


@pytest.fixture
def repository() -> AsyncMock:
    repo = AsyncMock()
    repo.database_is_available.return_value = True
    repo.cache_is_available.return_value = True
    return repo


@pytest.mark.asyncio
async def test_readiness_returns_ready_when_everything_available(repository: AsyncMock) -> None:
    service = HealthService(repository)
    result = await service.readiness()
    assert result == Readiness(database=True, redis=True)
    assert result.ready


@pytest.mark.asyncio
async def test_readiness_returns_not_ready_when_database_down(repository: AsyncMock) -> None:
    repository.database_is_available.return_value = False
    service = HealthService(repository)
    result = await service.readiness()
    assert not result.ready
    assert not result.database
    assert result.redis


@pytest.mark.asyncio
async def test_readiness_returns_not_ready_when_redis_down(repository: AsyncMock) -> None:
    repository.cache_is_available.return_value = False
    service = HealthService(repository)
    result = await service.readiness()
    assert not result.ready
    assert result.database
    assert not result.redis
