import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.audit import AuditLog
from titan_x.models.job import Job, JobExecution
from titan_x.models.monitoring import SystemMetric
from titan_x.models.user import User
from titan_x.services.monitoring_service import MonitoringService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def user(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        u = User(email="monitor@test.com", hashed_password="pw")
        s.add(u)
        await s.commit()
        yield u
        await s.close()


@pytest_asyncio.fixture
async def session(engine, user):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def service(session):
    return MonitoringService(session)


class TestSystemMetric:
    async def test_record_metric(self, service, session):
        m = await service.record_metric("cpu_percent", 45.2, tags={"host": "web-1"})
        assert m.id is not None
        assert m.metric_name == "cpu_percent"
        assert m.metric_value == 45.2
        assert json.loads(m.tags_json) == {"host": "web-1"}

    async def test_record_metric_no_tags(self, service, session):
        m = await service.record_metric("memory_mb", 1024.0)
        assert m.metric_value == 1024.0
        assert m.tags_json is None

    async def test_get_metric_history(self, service, session):
        for i in range(5):
            await service.record_metric("cpu_percent", float(50 + i))
        metrics = await service.get_metric_history("cpu_percent", limit=3)
        assert len(metrics) == 3
        assert all(m.metric_name == "cpu_percent" for m in metrics)

    async def test_get_metric_history_with_time_range(self, service, session):
        await service.record_metric("latency_ms", 10.0)
        old = await service.record_metric("latency_ms", 20.0)
        old.recorded_at = datetime.now(timezone.utc) - timedelta(days=2)
        session.add(old)
        await session.flush()
        since = datetime.now(timezone.utc) - timedelta(days=1)
        metrics = await service.get_metric_history("latency_ms", since=since)
        assert len(metrics) == 1
        assert metrics[0].metric_value == 10.0

    async def test_get_metric_stats(self, service, session):
        for v in [10.0, 20.0, 30.0]:
            await service.record_metric("test_metric", v)
        stats = await service.get_metric_stats("test_metric")
        assert stats["count"] == 3
        assert stats["avg"] == 20.0
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0

    async def test_get_metric_stats_empty(self, service, session):
        stats = await service.get_metric_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["avg"] is None

    async def test_system_health_shape(self, service, session):
        health = await service.get_system_health()
        for key in ("cpu", "memory", "api_latency", "database", "queue", "scheduler", "recorded_at"):
            assert key in health
        assert health["database"]["available"] is True

    async def test_system_health_db_ping(self, service, session):
        health = await service.get_system_health()
        assert health["database"]["ping_ms"] is not None
        assert health["database"]["ping_ms"] >= 0

    async def test_system_health_api_latency_no_data(self, service, session):
        health = await service.get_system_health()
        assert health["api_latency"]["avg_latency_ms"] is None
        assert health["api_latency"]["requests_last_5min"] == 0

    async def test_system_health_scheduler(self, service, session):
        job = Job(name="test-job", job_type="test", schedule_type="cron", cron_expr="*/5 * * * *")
        session.add(job)
        await session.flush()
        health = await service.get_system_health()
        assert health["scheduler"]["total_jobs"] >= 1
        assert health["scheduler"]["enabled_jobs"] >= 0
        assert "recent_executions" in health["scheduler"]

    async def test_system_health_queue(self, service, session):
        job = Job(name="queued-job", job_type="test", schedule_type="cron", cron_expr="*/5 * * * *", last_status="running")
        session.add(job)
        await session.flush()
        health = await service.get_system_health()
        assert health["queue"]["available"] is True
        assert health["queue"]["running_jobs"] >= 1

    async def test_system_health_cpu_memory(self, service, session):
        health = await service.get_system_health()
        assert health["cpu"]["available"] is True
        assert health["memory"]["available"] is True
        assert health["cpu"]["percent"] is not None
        assert health["memory"]["total_gb"] is not None

    async def test_system_health_scheduler_with_executions(self, service, session):
        job = Job(name="exec-job", job_type="test", schedule_type="cron", cron_expr="*/5 * * * *", enabled=True)
        session.add(job)
        await session.flush()
        exec1 = JobExecution(job_id=job.id, job_name="exec-job", status="completed", duration_ms=150)
        exec2 = JobExecution(job_id=job.id, job_name="exec-job", status="failed", duration_ms=200)
        session.add_all([exec1, exec2])
        await session.flush()
        health = await service.get_system_health()
        assert health["scheduler"]["total_failed_executions"] >= 1
        assert len(health["scheduler"]["recent_executions"]) >= 2

    async def test_record_and_retrieve_with_tags(self, service, session):
        m = await service.record_metric("request_latency", 12.3, tags={"endpoint": "/api/v1/test", "method": "POST"})
        fetched = (await session.execute(select(SystemMetric).where(SystemMetric.id == m.id))).scalar_one()
        assert json.loads(fetched.tags_json)["endpoint"] == "/api/v1/test"
        assert json.loads(fetched.tags_json)["method"] == "POST"

    # --- api_latency_with_data uses the module-level `user` fixture ---
    async def test_system_health_api_latency_with_data(self, service, session, user):
        log = AuditLog(
            user_id=user.id, entity_type="system", category="api_call", severity="info",
            action="GET /test", details_json=json.dumps({"duration_ms": 42.5}),
        )
        session.add(log)
        await session.flush()
        health = await service.get_system_health()
        assert health["api_latency"]["requests_last_5min"] >= 1
        assert health["api_latency"]["avg_latency_ms"] is not None
