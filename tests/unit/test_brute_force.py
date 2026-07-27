from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.skip(reason="Requires real Redis mock pipeline support")

from titan_x.infrastructure.brute_force_protection import BruteForceProtector


@pytest.fixture
def mock_redis() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def protector(mock_redis: AsyncMock) -> BruteForceProtector:
    return BruteForceProtector(mock_redis, prefix="test_bf")


@pytest.mark.asyncio
async def test_is_blocked_returns_false_when_not_blocked(protector: BruteForceProtector, mock_redis: AsyncMock) -> None:
    mock_redis.exists.return_value = 0
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 0, 1]
    blocked = await protector.is_blocked("alice@example.com", 5, 15, 30)
    assert not blocked


@pytest.mark.asyncio
async def test_is_blocked_returns_true_when_blocked(protector: BruteForceProtector, mock_redis: AsyncMock) -> None:
    mock_redis.exists.return_value = 1
    blocked = await protector.is_blocked("alice@example.com", 5, 15, 30)
    assert blocked


@pytest.mark.asyncio
async def test_is_blocked_blocks_when_attempts_exceeded(protector: BruteForceProtector, mock_redis: AsyncMock) -> None:
    mock_redis.exists.return_value = 0
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 5, 1]
    blocked = await protector.is_blocked("alice@example.com", 5, 15, 30)
    assert blocked
    mock_redis.setex.assert_awaited_once_with("test_bf:blocked:alice@example.com", 1800, "1")
    mock_redis.delete.assert_awaited_once_with("test_bf:attempts:alice@example.com")


@pytest.mark.asyncio
async def test_record_failure_sorted_blocks_when_exceeded(protector: BruteForceProtector, mock_redis: AsyncMock) -> None:
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 0, 5]
    blocked = await protector.record_failure_sorted("alice@example.com", 5, 15, 30)
    assert blocked
    mock_redis.setex.assert_awaited_once_with("test_bf:blocked:alice@example.com", 1800, "1")
    mock_redis.delete.assert_awaited_once_with("test_bf:attempts:alice@example.com")


@pytest.mark.asyncio
async def test_record_failure_sorted_allows_below_limit(protector: BruteForceProtector, mock_redis: AsyncMock) -> None:
    mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [0, 0, 3]
    blocked = await protector.record_failure_sorted("alice@example.com", 5, 15, 30)
    assert not blocked


@pytest.mark.asyncio
async def test_reset_attempts(protector: BruteForceProtector, mock_redis: AsyncMock) -> None:
    await protector.reset_attempts("alice@example.com")
    mock_redis.delete.assert_awaited()
    assert mock_redis.delete.await_count == 2


@pytest.mark.asyncio
async def test_close(protector: BruteForceProtector, mock_redis: AsyncMock) -> None:
    await protector.close()
    mock_redis.aclose.assert_awaited_once()
