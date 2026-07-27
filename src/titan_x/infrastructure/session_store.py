import json
import time
from typing import Any

from redis.asyncio import Redis


class RedisSessionStore:
    def __init__(self, redis: Redis, prefix: str = "sess", default_ttl: int = 3600) -> None:
        self._redis = redis
        self._prefix = prefix
        self.default_ttl = default_ttl

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}"

    async def create(self, session_id: str, data: dict[str, Any], ttl: int | None = None) -> None:
        payload: dict[str, Any] = {
            "data": data,
            "created_at": time.time(),
        }
        await self._redis.setex(self._key(session_id), ttl or self.default_ttl, json.dumps(payload, default=str))

    async def get(self, session_id: str) -> dict[str, Any] | None:
        raw: str | None = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        try:
            payload: dict[str, Any] = json.loads(raw)
            return payload["data"]
        except (json.JSONDecodeError, KeyError):
            return None

    async def update(self, session_id: str, data: dict[str, Any], ttl: int | None = None) -> None:
        existing: dict[str, Any] | None = await self.get(session_id)
        if existing is None:
            return
        existing.update(data)
        payload: dict[str, Any] = {
            "data": existing,
            "created_at": time.time(),
        }
        await self._redis.setex(self._key(session_id), ttl or self.default_ttl, json.dumps(payload, default=str))

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def exists(self, session_id: str) -> bool:
        return bool(await self._redis.exists(self._key(session_id)))

    async def refresh_ttl(self, session_id: str, ttl: int | None = None) -> None:
        await self._redis.expire(self._key(session_id), ttl or self.default_ttl)

    async def clear_all(self) -> None:
        cursor: int = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=f"{self._prefix}:*")
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    async def close(self) -> None:
        await self._redis.aclose()
