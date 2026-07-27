from datetime import datetime, timezone

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.jobs.base import ScheduledJob
from titan_x.models.job import Job
from titan_x.models.user import User

logger = structlog.get_logger(__name__)


class SyncJobDefinitionsJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("sync_job_definitions", "cron", max_retries=2, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        session: AsyncSession = payload["session"]
        repo = BaseRepository(session, Job)
        result = await session.execute(select(func.count()).select_from(Job))
        count: int = result.scalar() or 0
        return {"job_count": count}


class HeartbeatJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("heartbeat", "cron", max_retries=1, retry_delay=10)

    async def _run(self, payload: dict) -> dict:
        now: str = datetime.now(timezone.utc).isoformat()
        logger.info("heartbeat", timestamp=now)
        return {"timestamp": now}


class ActiveUserCountJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("active_user_count", "cron", max_retries=2, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        session: AsyncSession = payload["session"]
        result = await session.execute(select(func.count()).where(User.is_active.is_(True)))
        count: int = result.scalar() or 0
        logger.info("active_user_count", count=count)
        return {"active_users": count}
