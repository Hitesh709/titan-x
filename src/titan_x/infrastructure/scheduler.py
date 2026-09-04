import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from croniter import croniter
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_x.infrastructure.task_queue import TaskQueue
from titan_x.models.job import Job, JobExecution

logger = structlog.get_logger(__name__)


class Scheduler:
    def __init__(
        self,
        redis: Redis,
        task_queue: TaskQueue,
        session_factory: async_sessionmaker[AsyncSession],
        poll_interval: int = 15,
        prefix: str = "sched",
    ) -> None:
        self._redis = redis
        self._queue = task_queue
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._prefix = prefix
        self._running = False
        self._registered_jobs: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {}

    def register_job(self, job_type: str, handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self._registered_jobs[job_type] = handler
        logger.info("job_registered", job_type=job_type)

    async def start(self) -> None:
        self._running = True
        logger.info("scheduler_started", poll_interval=self._poll_interval)
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                async with self._session_factory() as session:
                    result = await session.execute(
                        select(Job).where(
                            Job.enabled.is_(True),
                            Job.next_run_at.isnot(None),
                            Job.next_run_at <= now,
                        )
                    )
                    due_jobs: list[Job] = list(result.scalars().all())

                for job_def in due_jobs:
                    await self._dispatch_job(job_def, now)

                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("scheduler_loop_error")
                await asyncio.sleep(self._poll_interval)

    async def _dispatch_job(self, job_def: Job, now: datetime) -> None:
        lock_key: str = f"{self._prefix}:lock:{job_def.id}"
        locked: bool = await self._redis.setnx(lock_key, "1")
        if not locked:
            return

        await self._redis.expire(lock_key, 300)

        try:
            next_run = self._calculate_next_run(job_def, now)
            job_def.last_run_at = now
            job_def.run_count += 1
            job_def.last_status = "running"
            # Advance the schedule before enqueueing so a job cannot be
            # dispatched repeatedly while the worker is processing it.
            job_def.next_run_at = next_run
            async with self._session_factory() as session:
                session.add(job_def)
                await session.commit()

            await self._queue.enqueue(
                queue_name="scheduled_jobs",
                task_type=job_def.job_type,
                payload={
                    "job_id": job_def.id,
                    "job_name": job_def.name,
                    "job_type": job_def.job_type,
                },
            )
            logger.info("job_dispatched", job_id=job_def.id, job_name=job_def.name, job_type=job_def.job_type)
        except Exception as exc:
            logger.error("job_dispatch_failed", job_id=job_def.id, error=str(exc))
        finally:
            await self._redis.delete(lock_key)

    async def handle_completion(
        self,
        job_id: int,
        status: str,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            result = await session.execute(select(Job).where(Job.id == job_id))
            job_def: Job | None = result.scalar_one_or_none()
            if job_def is None:
                logger.warning("job_not_found", job_id=job_id)
                return

            job_def.last_status = status
            if status == "failed":
                job_def.failure_count += 1
                job_def.last_error = error

            # Recalculate from the completion time only when the previous
            # dispatch did not already advance the schedule.
            if job_def.next_run_at is None or job_def.next_run_at <= datetime.now(timezone.utc):
                job_def.next_run_at = self._calculate_next_run(job_def)
            session.add(job_def)

            execution = JobExecution(
                job_id=job_id,
                job_name=job_def.name,
                status=status,
                duration_ms=duration_ms,
                error=error,
            )
            session.add(execution)
            await session.commit()
            logger.info("job_completion_recorded", job_id=job_id, status=status)

    def _calculate_next_run(self, job_def: Job, now: datetime | None = None) -> datetime | None:
        if not job_def.enabled:
            return None
        now = now or datetime.now(timezone.utc)
        if job_def.schedule_type == "daily" and job_def.schedule_time:
            parts = job_def.schedule_time.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run
        if job_def.schedule_type == "cron" and job_def.cron_expr:
            try:
                return croniter(job_def.cron_expr, now).get_next(datetime)
            except (ValueError, KeyError) as exc:
                logger.error("invalid_cron_expression", job_id=job_def.id, expression=job_def.cron_expr, error=str(exc))
                return None
        if job_def.schedule_type == "market":
            next_run = now.replace(hour=9, minute=30, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)
            return next_run
        return None

    async def stop(self) -> None:
        self._running = False
        logger.info("scheduler_stopped")
