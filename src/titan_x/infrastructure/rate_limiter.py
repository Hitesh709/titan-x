import time
from typing import Any

from redis.asyncio import Redis


class RateLimiter:
    def __init__(self, redis: Redis, prefix: str = "rl") -> None:
        self._redis = redis
        self._prefix = prefix

    async def check(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        now: int = int(time.time())
        window_start: int = now - window_seconds
        redis_key: str = f"{self._prefix}:{key}"

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(now): now})
            pipe.expire(redis_key, window_seconds)
            results: list[Any] = await pipe.execute()

        current_count: int = results[1]
        allowed: bool = current_count <= max_requests
        remaining: int = max(0, max_requests - current_count)
        return allowed, remaining, window_seconds

    async def close(self) -> None:
        await self._redis.aclose()
