"""Distributed API rate limiting with Redis and a safe local fallback."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

import redis.asyncio as redis
from fastapi import HTTPException, Request
from redis.exceptions import RedisError


class RateLimiter:
    """Fixed-window limiter shared through Redis when available.

    A local limiter remains available so a temporary Redis outage does not take
    the API offline. Redis is the source of truth when the connection succeeds.
    """

    def __init__(self, limit: int = 120, window_seconds: int = 60, redis_url: str | None = None):
        self.limit = limit
        self.window = window_seconds
        self.redis = (
            redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            if redis_url
            else None
        )
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    @staticmethod
    def _client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    async def check(self, request: Request) -> None:
        client_key = self._client_key(request)

        if self.redis is not None:
            redis_key = f"titanx:ratelimit:{client_key}"
            try:
                count = int(await self.redis.incr(redis_key))
                if count == 1:
                    await self.redis.expire(redis_key, self.window)
                if count > self.limit:
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")
                return
            except HTTPException:
                raise
            except (RedisError, OSError, TimeoutError):
                # Fall through to the local limiter during a Redis outage.
                pass

        self._check_local(client_key)

    def _check_local(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            q.append(now)
