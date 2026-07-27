from typing import Protocol

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository(Protocol):
    async def database_is_available(self) -> bool: ...

    async def cache_is_available(self) -> bool: ...


class SqlAlchemyRedisHealthRepository:
    """Health adapter that verifies the two required infrastructure services."""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis

    async def database_is_available(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    async def cache_is_available(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False
