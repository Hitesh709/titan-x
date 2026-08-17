import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


class RedisCache:
    def __init__(self, redis: Redis, prefix: str = "cache") -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str, default: Any = None) -> Any:
        try:
            data: str | None = await self._redis.get(self._key(key))
        except Exception:  # noqa: BLE001
            logger.warning("redis_get_failed", key=key)
            return default
        if data is None:
            return default
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            serialized: str = json.dumps(value, default=str)
        except (TypeError, ValueError):
            logger.warning("redis_set_serialize_failed", key=key)
            return
        try:
            if ttl is not None:
                await self._redis.setex(self._key(key), ttl, serialized)
            else:
                await self._redis.set(self._key(key), serialized)
        except Exception:  # noqa: BLE001
            logger.warning("redis_set_failed", key=key)

    async def delete(self, key: str) -> None:
        await self._redis.delete(self._key(key))

    async def clear(self) -> None:
        cursor: int = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=f"{self._prefix}:*")
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(self._key(key)))

    async def ttl(self, key: str) -> int:
        return await self._redis.ttl(self._key(key))

    async def close(self) -> None:
        await self._redis.aclose()


class MemoryCache:
    """Process-local fallback used when Redis is unavailable.

    Unlike a mock, ``get`` returns ``None`` (a real cache miss) so callers that
    do ``if cached is not None: return cached`` behave correctly instead of
    returning a truthy mock object (which previously produced 500s).
    """

    def __init__(self, prefix: str = "cache") -> None:
        self._prefix = prefix
        self._store: dict[str, Any] = {}

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(self._key(key), default)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._store[self._key(key)] = value

    async def delete(self, key: str) -> None:
        self._store.pop(self._key(key), None)

    async def clear(self) -> None:
        self._store.clear()

    async def exists(self, key: str) -> bool:
        return self._key(key) in self._store

    async def ttl(self, key: str) -> int:
        return -1


def cached(cache: RedisCache, ttl: int | None = None, key_builder: Callable[..., str] | None = None) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key: str = key_builder(*args, **kwargs) if key_builder else f"{func.__name__}:{hash(frozenset(kwargs.items()))}"
            result: Any = await cache.get(cache_key)
            if result is not None:
                return result
            result = await func(*args, **kwargs)
            asyncio.ensure_future(cache.set(cache_key, result, ttl))
            return result
        return wrapper  # type: ignore[return-value]
    return decorator