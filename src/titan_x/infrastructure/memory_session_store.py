"""Process-local session store used only when Redis is unavailable."""

import time
from typing import Any


class MemorySessionStore:
    """Safe development/free-tier fallback for short-lived sessions.

    This is intentionally process-local and must not be treated as a durable
    distributed session store. Production deployments should provide Redis.
    """

    def __init__(self, default_ttl: int = 3600) -> None:
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}

    def _purge(self) -> None:
        now = time.time()
        expired = [key for key, (expires_at, _) in self._store.items() if expires_at <= now]
        for key in expired:
            self._store.pop(key, None)

    async def create(self, session_id: str, data: dict[str, Any], ttl: int | None = None) -> None:
        self._purge()
        self._store[session_id] = (time.time() + (ttl or self.default_ttl), dict(data))

    async def get(self, session_id: str) -> dict[str, Any] | None:
        self._purge()
        item = self._store.get(session_id)
        return None if item is None else dict(item[1])

    async def update(self, session_id: str, data: dict[str, Any], ttl: int | None = None) -> None:
        existing = await self.get(session_id)
        if existing is None:
            return
        existing.update(data)
        await self.create(session_id, existing, ttl)

    async def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    async def exists(self, session_id: str) -> bool:
        return await self.get(session_id) is not None

    async def refresh_ttl(self, session_id: str, ttl: int | None = None) -> None:
        existing = await self.get(session_id)
        if existing is not None:
            await self.create(session_id, existing, ttl)

    async def clear_all(self) -> None:
        self._store.clear()

    async def close(self) -> None:
        self._store.clear()
