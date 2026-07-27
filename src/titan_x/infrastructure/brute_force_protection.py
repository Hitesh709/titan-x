import time
from typing import Any

from redis.asyncio import Redis


class BruteForceProtector:
    def __init__(self, redis: Redis, prefix: str = "bf") -> None:
        self._redis = redis
        self._prefix = prefix

    async def record_failure(self, identifier: str) -> int:
        now: int = int(time.time())
        redis_key: str = f"{self._prefix}:attempts:{identifier}"

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.lpush(redis_key, now)
            pipe.ltrim(redis_key, 0, 999)
            pipe.llen(redis_key)
            pipe.expire(redis_key, 86400)
            results: list[Any] = await pipe.execute()

        return results[2]

    async def is_blocked(self, identifier: str, max_attempts: int, window_minutes: int, block_minutes: int) -> bool:
        block_key: str = f"{self._prefix}:blocked:{identifier}"
        blocked: int = await self._redis.exists(block_key)
        if blocked:
            return True

        attempts_key: str = f"{self._prefix}:attempts:{identifier}"
        cutoff: float = time.time() - (window_minutes * 60)

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(attempts_key, 0, cutoff)
            pipe.zcard(attempts_key)
            pipe.expire(attempts_key, 86400)
            counts: list[Any] = await pipe.execute()

        if counts[1] >= max_attempts:
            await self._redis.setex(block_key, block_minutes * 60, "1")
            await self._redis.delete(attempts_key)
            return True

        return False

    async def record_failure_sorted(self, identifier: str, max_attempts: int, window_minutes: int, block_minutes: int) -> bool:
        now: int = int(time.time())
        window_start: int = now - (window_minutes * 60)
        redis_key: str = f"{self._prefix}:attempts:{identifier}"

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_minutes * 60 + 60)
            results = await pipe.execute()

        attempt_count: int = results[2]
        if attempt_count >= max_attempts:
            block_key: str = f"{self._prefix}:blocked:{identifier}"
            await self._redis.setex(block_key, block_minutes * 60, "1")
            await self._redis.delete(redis_key)
            return True

        return False

    async def reset_attempts(self, identifier: str) -> None:
        await self._redis.delete(f"{self._prefix}:attempts:{identifier}")
        await self._redis.delete(f"{self._prefix}:blocked:{identifier}")

    async def close(self) -> None:
        await self._redis.aclose()
