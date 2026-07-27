from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.jobs.base import BaseJob
from titan_x.models.job import Job, JobExecution

logger = structlog.get_logger(__name__)


class SchedulerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._job_repo = BaseRepository(session, Job)
        self._execution_repo = BaseRepository(session, JobExecution)

    async def create_job(self, name: str, job_type: str, schedule_type: str, **kwargs: Any) -> Job:
        existing = await self._job_repo.get_multi(name=name, limit=1)
        if existing:
            raise ValueError(f"Job '{name}' already exists")
        return await self._job_repo.create(
            name=name,
            job_type=job_type,
            schedule_type=schedule_type,
            **kwargs,
        )

    async def get_job(self, job_id: int) -> Job | None:
        return await self._job_repo.get(job_id)

    async def list_jobs(self, skip: int = 0, limit: int = 100) -> list[Job]:
        result = await self._job_repo.get_multi(skip=skip, limit=limit)
        return list(result)

    async def update_job(self, job_id: int, **kwargs: Any) -> Job | None:
        return await self._job_repo.update(job_id, **kwargs)

    async def delete_job(self, job_id: int) -> bool:
        return await self._job_repo.delete(job_id)

    async def enable_job(self, job_id: int) -> Job | None:
        return await self._job_repo.update(job_id, enabled=True)

    async def disable_job(self, job_id: int) -> Job | None:
        return await self._job_repo.update(job_id, enabled=False)

    async def get_executions(self, job_id: int, skip: int = 0, limit: int = 50) -> list[JobExecution]:
        result = await self._execution_repo.get_multi(job_id=job_id, skip=skip, limit=limit, order_by="started_at", descending=True)
        return list(result)

    async def get_run_history(self, skip: int = 0, limit: int = 100) -> list[JobExecution]:
        result = await self._execution_repo.get_multi(skip=skip, limit=limit, order_by="started_at", descending=True)
        return list(result)

    async def get_job_stats(self) -> dict[str, Any]:
        total = await self._job_repo.count()
        enabled = await self._job_repo.count(enabled=True)
        running = await self._job_repo.count(last_status="running")
        failed = await self._job_repo.count(last_status="failed")
        return {"total_jobs": total, "enabled_jobs": enabled, "running_jobs": running, "failed_jobs": failed}

    async def get_execution_stats(self) -> dict[str, Any]:
        total = await self._execution_repo.count()
        failed_count = await self._execution_repo.count(status="failed")
        success_count = await self._execution_repo.count(status="success")
        return {"total_executions": total, "successful": success_count, "failed": failed_count}

    async def run_job_now(self, job_id: int) -> None:
        job = await self._job_repo.get(job_id)
        if job is None:
            raise ValueError("Job not found")
        now = datetime.now(timezone.utc)
        await self._job_repo.update(job_id, last_run_at=now, last_status="running", run_count=job.run_count + 1)
