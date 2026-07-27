from unittest.mock import AsyncMock

import pytest

from titan_x.infrastructure.session_store import RedisSessionStore


@pytest.fixture
def mock_redis() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def store(mock_redis: AsyncMock) -> RedisSessionStore:
    return RedisSessionStore(mock_redis, prefix="test_sess", default_ttl=3600)


@pytest.mark.asyncio
async def test_create_stores_session(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    await store.create("sess-1", {"user_id": 1, "role": "admin"})
    mock_redis.setex.assert_awaited_once()
    args, _ = mock_redis.setex.await_args
    assert args[0] == "test_sess:sess-1"
    assert args[1] == 3600
    assert '"user_id"' in args[2]
    assert '"role"' in args[2]


@pytest.mark.asyncio
async def test_get_returns_data_when_exists(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = '{"data": {"user_id": 1}, "created_at": 1000.0}'
    data = await store.get("sess-1")
    assert data == {"user_id": 1}


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = None
    data = await store.get("sess-1")
    assert data is None


@pytest.mark.asyncio
async def test_update_merges_data(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = '{"data": {"user_id": 1, "name": "alice"}, "created_at": 1000.0}'
    await store.update("sess-1", {"name": "bob", "role": "admin"})
    mock_redis.setex.assert_awaited_once()
    args, _ = mock_redis.setex.await_args
    assert '"name"' in args[2]
    assert '"bob"' in args[2]
    assert '"role"' in args[2]
    assert '"user_id"' in args[2]


@pytest.mark.asyncio
async def test_update_does_nothing_when_session_missing(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    mock_redis.get.return_value = None
    await store.update("sess-1", {"role": "admin"})
    mock_redis.setex.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    await store.delete("sess-1")
    mock_redis.delete.assert_awaited_once_with("test_sess:sess-1")


@pytest.mark.asyncio
async def test_exists(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    mock_redis.exists.return_value = 1
    assert await store.exists("sess-1")
    mock_redis.exists.return_value = 0
    assert not await store.exists("sess-2")


@pytest.mark.asyncio
async def test_refresh_ttl(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    await store.refresh_ttl("sess-1", ttl=7200)
    mock_redis.expire.assert_awaited_once_with("test_sess:sess-1", 7200)


@pytest.mark.asyncio
async def test_refresh_ttl_uses_default(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    await store.refresh_ttl("sess-1")
    mock_redis.expire.assert_awaited_once_with("test_sess:sess-1", 3600)


@pytest.mark.asyncio
async def test_clear_all(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    mock_redis.scan.return_value = (0, ["test_sess:a", "test_sess:b"])
    await store.clear_all()
    mock_redis.delete.assert_awaited_once_with("test_sess:a", "test_sess:b")


@pytest.mark.asyncio
async def test_close(store: RedisSessionStore, mock_redis: AsyncMock) -> None:
    await store.close()
    mock_redis.aclose.assert_awaited_once()
