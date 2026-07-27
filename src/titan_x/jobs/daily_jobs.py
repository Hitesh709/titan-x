from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.jobs.base import ScheduledJob
from titan_x.models.job import JobExecution
from titan_x.models.refresh_token import RefreshToken

logger = structlog.get_logger(__name__)


class CleanupExpiredTokensJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("cleanup_expired_tokens", "daily", max_retries=2, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        session: AsyncSession = payload["session"]
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        deleted: int = result.rowcount
        logger.info("expired_tokens_cleaned", count=deleted)
        return {"tokens_deleted": deleted}


class DatabaseHealthCheckJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("database_health_check", "daily", max_retries=1, retry_delay=10)

    async def _run(self, payload: dict) -> dict:
        session: AsyncSession = payload["session"]
        result = await session.execute(delete(JobExecution).where("1=0"))
        return {"healthy": True}


class PruneOldExecutionsJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("prune_old_executions", "daily", max_retries=2, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        session: AsyncSession = payload["session"]
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        stmt = delete(JobExecution).where(JobExecution.started_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        deleted: int = result.rowcount
        logger.info("old_executions_pruned", count=deleted)
        return {"executions_deleted": deleted}
