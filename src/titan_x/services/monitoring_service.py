import json
import os
import time
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.audit import AuditLog
from titan_x.models.job import Job, JobExecution
from titan_x.models.monitoring import SystemMetric

logger = structlog.get_logger(__name__)

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class MonitoringService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._metric_repo = BaseRepository(session, SystemMetric)

    async def record_metric(
        self, name: str, value: float, tags: dict[str, str] | None = None,
    ) -> SystemMetric:
        return await self._metric_repo.create(
            metric_name=name,
            metric_value=value,
            tags_json=json.dumps(tags) if tags else None,
        )

    async def get_system_health(self) -> dict[str, Any]:
        cpu = await self._get_cpu()
        memory = await self._get_memory()
        api_latency = await self._get_api_latency()
        db_perf = await self._get_db_performance()
        queue = await self._get_queue_health()
        scheduler = await self._get_scheduler_health()
        return {
            "cpu": cpu,
            "memory": memory,
            "api_latency": api_latency,
            "database": db_perf,
            "queue": queue,
            "scheduler": scheduler,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_cpu(self) -> dict[str, Any]:
        if not HAS_PSUTIL:
            return {"available": False, "message": "psutil not installed"}
        try:
            return {
                "available": True,
                "percent": psutil.cpu_percent(interval=0.1),
                "count": psutil.cpu_count(),
                "frequency_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None,
                "load_avg_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _get_memory(self) -> dict[str, Any]:
        if not HAS_PSUTIL:
            return {"available": False, "message": "psutil not installed"}
        try:
            mem = psutil.virtual_memory()
            return {
                "available": True,
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "percent": mem.percent,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _get_api_latency(self) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        try:
            result = await self._session.execute(
                select(func.avg(text("CAST(JSON_EXTRACT(details_json, '$.duration_ms') AS FLOAT)")))
                .select_from(AuditLog)
                .where(
                    AuditLog.category == "api_call",
                    AuditLog.created_at >= cutoff,
                    AuditLog.details_json.isnot(None),
                )
            )
            avg_latency = result.scalar()
        except Exception:
            avg_latency = None
        count = 0
        try:
            cnt_result = await self._session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.category == "api_call", AuditLog.created_at >= cutoff)
            )
            count = cnt_result.scalar() or 0
        except Exception:
            pass
        return {
            "avg_latency_ms": round(avg_latency, 2) if avg_latency is not None else None,
            "requests_last_5min": count,
            "window_minutes": 5,
        }

    async def _get_db_performance(self) -> dict[str, Any]:
        start = time.monotonic()
        try:
            await self._session.execute(text("SELECT 1"))
            query_time_ms = (time.monotonic() - start) * 1000
        except Exception as e:
            return {"available": False, "error": str(e)}
        pool = self._session.get_bind().pool
        pool_size = getattr(pool, "size", lambda: None)()
        checkedin = getattr(pool, "checkedin", lambda: None)()
        overflow = getattr(pool, "overflow", lambda: None)()
        return {
            "available": True,
            "ping_ms": round(query_time_ms, 2),
            "pool_size": pool_size,
            "checkedin": checkedin,
            "overflow": overflow,
        }

    async def _get_queue_health(self) -> dict[str, Any]:
        try:
            total = await self._session.execute(
                select(func.count()).select_from(Job).where(Job.last_status == "running")
            )
            running_jobs = total.scalar() or 0
        except Exception:
            running_jobs = None
        return {
            "available": True,
            "running_jobs": running_jobs,
            "note": "Redis-backed queue (use /api/v1/monitoring/queues for Redis metrics)",
        }

    async def _get_scheduler_health(self) -> dict[str, Any]:
        try:
            total = (await self._session.execute(select(func.count()).select_from(Job))).scalar() or 0
            enabled = (await self._session.execute(
                select(func.count()).select_from(Job).where(Job.enabled.is_(True))
            )).scalar() or 0
            failed = (await self._session.execute(
                select(func.count()).select_from(JobExecution).where(JobExecution.status == "failed")
            )).scalar() or 0
            recent = (await self._session.execute(
                select(JobExecution).order_by(JobExecution.started_at.desc()).limit(5)
            )).scalars().all()
        except Exception as e:
            return {"available": False, "error": str(e)}
        return {
            "available": True,
            "total_jobs": total,
            "enabled_jobs": enabled,
            "total_failed_executions": failed,
            "recent_executions": [
                {
                    "job_name": e.job_name,
                    "status": e.status,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "duration_ms": e.duration_ms,
                }
                for e in recent
            ],
        }

    async def get_metric_history(
        self, metric_name: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> Sequence[SystemMetric]:
        stmt = select(SystemMetric).where(SystemMetric.metric_name == metric_name)
        if since:
            stmt = stmt.where(SystemMetric.recorded_at >= since)
        if until:
            stmt = stmt.where(SystemMetric.recorded_at <= until)
        stmt = stmt.order_by(SystemMetric.recorded_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_metric_stats(
        self, metric_name: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            func.count(), func.avg(SystemMetric.metric_value),
            func.min(SystemMetric.metric_value), func.max(SystemMetric.metric_value),
        ).where(SystemMetric.metric_name == metric_name)
        if since:
            stmt = stmt.where(SystemMetric.recorded_at >= since)
        if until:
            stmt = stmt.where(SystemMetric.recorded_at <= until)
        result = (await self._session.execute(stmt)).one()
        return {
            "metric_name": metric_name,
            "count": result[0] or 0,
            "avg": round(result[1], 4) if result[1] is not None else None,
            "min": round(result[2], 4) if result[2] is not None else None,
            "max": round(result[3], 4) if result[3] is not None else None,
        }
