from unittest.mock import AsyncMock

import pytest

from titan_x.infrastructure.cache import RedisCache


@pytest.fixture
def mock_redis() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def cache(mock_redis: AsyncMock) -> RedisCache:
    return RedisCache(mock_redis, prefix="test_cache")


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(cache: RedisCache, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = None
    result = await cache.get("missing-key")
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_default_when_missing(cache: RedisCache, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = None
    result = await cache.get("missing-key", default="fallback")
    assert result == "fallback"


@pytest.mark.asyncio
async def test_get_returns_deserialized_value(cache: RedisCache, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = '{"name": "test", "count": 42}'
    result = await cache.get("existing-key")
    assert result == {"name": "test", "count": 42}


@pytest.mark.asyncio
async def test_set_stores_serialized_value(cache: RedisCache, mock_redis: AsyncMock) -> None:
    await cache.set("key", {"foo": "bar"})
    mock_redis.set.assert_awaited_once_with("test_cache:key", '{"foo": "bar"}')


@pytest.mark.asyncio
async def test_set_with_ttl(cache: RedisCache, mock_redis: AsyncMock) -> None:
    await cache.set("key", "value", ttl=60)
    mock_redis.setex.assert_awaited_once_with("test_cache:key", 60, '"value"')


@pytest.mark.asyncio
async def test_delete(cache: RedisCache, mock_redis: AsyncMock) -> None:
    await cache.delete("key")
    mock_redis.delete.assert_awaited_once_with("test_cache:key")


@pytest.mark.asyncio
async def test_exists_returns_true(cache: RedisCache, mock_redis: AsyncMock) -> None:
    mock_redis.exists.return_value = 1
    assert await cache.exists("key")


@pytest.mark.asyncio
async def test_exists_returns_false(cache: RedisCache, mock_redis: AsyncMock) -> None:
    mock_redis.exists.return_value = 0
    assert not await cache.exists("key")


@pytest.mark.asyncio
async def test_ttl(cache: RedisCache, mock_redis: AsyncMock) -> None:
    mock_redis.ttl.return_value = 42
    ttl = await cache.ttl("key")
    assert ttl == 42


@pytest.mark.asyncio
async def test_clear_scans_and_deletes(cache: RedisCache, mock_redis: AsyncMock) -> None:
    mock_redis.scan.return_value = (0, ["test_cache:a", "test_cache:b"])
    await cache.clear()
    mock_redis.scan.assert_awaited()
    mock_redis.delete.assert_awaited_once_with("test_cache:a", "test_cache:b")


@pytest.mark.asyncio
async def test_close(cache: RedisCache, mock_redis: AsyncMock) -> None:
    await cache.close()
    mock_redis.aclose.assert_awaited_once()
