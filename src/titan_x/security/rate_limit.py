"""Small dependency-free in-process rate limiter.

For multi-instance production deployments, replace storage with Redis so limits
are shared across workers/instances.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int = 120, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            q.append(now)
