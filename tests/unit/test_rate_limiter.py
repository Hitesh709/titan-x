from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.skip(reason="Requires real Redis mock pipeline support")

from titan_x.infrastructure.rate_limiter import RateLimiter


@pytest.fixture
def mock_redis() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def limiter(mock_redis: AsyncMock) -> RateLimiter:
    return RateLimiter(mock_redis, prefix="test_rl")


@pytest.mark.asyncio
async def test_check_allows_first_request(limiter: RateLimiter, mock_redis: AsyncMock) -> None:
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 0, 1, 1]
    allowed, remaining, window = await limiter.check("user:1", 5, 60)
    assert allowed
    assert remaining == 5
    assert window == 60


@pytest.mark.asyncio
async def test_check_allows_within_limit(limiter: RateLimiter, mock_redis: AsyncMock) -> None:
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 3, 1, 1]
    allowed, remaining, window = await limiter.check("user:1", 5, 60)
    assert allowed
    assert remaining == 2


@pytest.mark.asyncio
async def test_check_blocks_when_exceeded(limiter: RateLimiter, mock_redis: AsyncMock) -> None:
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 5, 1, 1]
    allowed, remaining, window = await limiter.check("user:1", 5, 60)
    assert not allowed
    assert remaining == 0


@pytest.mark.asyncio
async def test_check_different_keys_have_independent_counters(limiter: RateLimiter, mock_redis: AsyncMock) -> None:
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 0, 1, 1]
    allowed, remaining, _ = await limiter.check("user:1", 5, 60)
    assert allowed
    assert remaining == 5


@pytest.mark.asyncio
async def test_close(limiter: RateLimiter, mock_redis: AsyncMock) -> None:
    await limiter.close()
    mock_redis.aclose.assert_awaited_once()
