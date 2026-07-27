from dataclasses import dataclass

from titan_x.infrastructure.health_repository import HealthRepository


@dataclass(frozen=True, slots=True)
class Readiness:
    database: bool
    redis: bool

    @property
    def ready(self) -> bool:
        return self.database and self.redis


class HealthService:
    """Coordinates system readiness checks without coupling to infrastructure."""

    def __init__(self, repository: HealthRepository) -> None:
        self._repository = repository

    async def readiness(self) -> Readiness:
        database = await self._repository.database_is_available()
        redis = await self._repository.cache_is_available()
        return Readiness(database=database, redis=redis)
