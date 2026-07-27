from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.audit import AuditLog
from titan_x.models.user import User
from titan_x.services.audit_service import AuditService

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
        u = User(email="audit@test.com", hashed_password="pw")
        s.add(u)
        await s.commit()
        yield u
        await s.close()


@pytest_asyncio.fixture
async def session(engine, user):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest.mark.asyncio
class TestLog:
    async def test_log_minimal(self, session, user):
        svc = AuditService(session)
        entry = await svc.log(action="test_action", entity_type="test_entity")
        assert entry.id is not None
        assert entry.action == "test_action"
        assert entry.entity_type == "test_entity"
        assert entry.category == "api_call"
        assert entry.severity == "info"

    async def test_log_full(self, session, user):
        svc = AuditService(session)
        entry = await svc.log(
            action="update", entity_type="strategy", entity_id=42,
            user_id=user.id, details_json='{"key":"val"}',
            ip_address="192.168.1.1", category="user_action", severity="warning",
        )
        assert entry.user_id == user.id
        assert entry.action == "update"
        assert entry.entity_type == "strategy"
        assert entry.entity_id == 42
        assert entry.details_json == '{"key":"val"}'
        assert entry.ip_address == "192.168.1.1"
        assert entry.category == "user_action"
        assert entry.severity == "warning"
        assert entry.created_at is not None

    async def test_to_dict(self, session, user):
        svc = AuditService(session)
        entry = await svc.log(action="view", entity_type="report", user_id=user.id)
        d = entry.to_dict()
        assert d["action"] == "view"
        assert d["user_id"] == user.id
        assert "created_at" in d


@pytest.mark.asyncio
class TestLogApiCall:
    async def test_info_severity(self, session):
        svc = AuditService(session)
        entry = await svc.log_api_call(user_id=1, method="GET", path="/api/v1/users", status_code=200, ip_address="10.0.0.1")
        assert entry.category == "api_call"
        assert entry.severity == "info"
        assert entry.action == "get"

    async def test_warning_severity(self, session):
        svc = AuditService(session)
        entry = await svc.log_api_call(user_id=1, method="POST", path="/api/v1/orders", status_code=400)
        assert entry.severity == "warning"

    async def test_critical_severity(self, session):
        svc = AuditService(session)
        entry = await svc.log_api_call(user_id=1, method="DELETE", path="/api/v1/admin", status_code=500)
        assert entry.severity == "critical"


@pytest.mark.asyncio
class TestLogUserAction:
    async def test_login_action(self, session, user):
        svc = AuditService(session)
        entry = await svc.log_user_action(user.id, "login", {"method": "password"}, "10.0.0.1")
        assert entry.category == "user_action"
        assert entry.action == "login"
        assert entry.user_id == user.id
        assert "password" in entry.details_json

    async def test_logout(self, session, user):
        svc = AuditService(session)
        entry = await svc.log_user_action(user.id, "logout")
        assert entry.action == "logout"


@pytest.mark.asyncio
class TestLogAIDecision:
    async def test_buy_decision(self, session):
        svc = AuditService(session)
        entry = await svc.log_ai_decision("AAPL", "buy", confidence=0.85, reasoning="Strong momentum")
        assert entry.category == "ai_decision"
        assert entry.action == "ai_buy"
        assert "AAPL" in entry.details_json

    async def test_sell_decision(self, session):
        svc = AuditService(session)
        entry = await svc.log_ai_decision("MSFT", "sell", confidence=0.7)
        assert entry.action == "ai_sell"


@pytest.mark.asyncio
class TestLogConfigChange:
    async def test_config_change(self, session, user):
        svc = AuditService(session)
        entry = await svc.log_config_change(user.id, "risk_tolerance", old_value="medium", new_value="high")
        assert entry.category == "config_change"
        assert entry.severity == "warning"
        assert "risk_tolerance" in entry.details_json
        assert "medium" in entry.details_json

    async def test_config_change_no_old(self, session, user):
        svc = AuditService(session)
        entry = await svc.log_config_change(user.id, "theme", new_value="dark")
        assert entry.action == "config_change"


@pytest.mark.asyncio
class TestLogSecurityEvent:
    async def test_failed_login(self, session):
        svc = AuditService(session)
        entry = await svc.log_security_event(
            "failed_login", {"username": "test@test.com", "reason": "bad_password"},
            ip_address="192.168.1.100", severity="warning",
        )
        assert entry.category == "security_event"
        assert entry.severity == "warning"
        assert entry.action == "failed_login"

    async def test_brute_force(self, session):
        svc = AuditService(session)
        entry = await svc.log_security_event("brute_force_detected", severity="critical")
        assert entry.severity == "critical"


@pytest.mark.asyncio
class TestListLogs:
    async def test_empty(self, session):
        svc = AuditService(session)
        logs, total = await svc.list_logs()
        assert logs == []
        assert total == 0

    async def test_filter_by_user(self, session, user):
        svc = AuditService(session)
        await svc.log(action="a1", entity_type="t", user_id=user.id)
        await svc.log(action="a2", entity_type="t")
        logs, total = await svc.list_logs(user_id=user.id)
        assert total == 1

    async def test_filter_by_category(self, session):
        svc = AuditService(session)
        await svc.log(action="a1", entity_type="t", category="api_call")
        await svc.log(action="a2", entity_type="t", category="user_action")
        logs, total = await svc.list_logs(category="user_action")
        assert total == 1
        assert logs[0].action == "a2"

    async def test_filter_by_severity(self, session):
        svc = AuditService(session)
        await svc.log(action="a1", entity_type="t", severity="info")
        await svc.log(action="a2", entity_type="t", severity="critical")
        logs, total = await svc.list_logs(severity="critical")
        assert total == 1

    async def test_filter_by_time_range(self, session):
        svc = AuditService(session)
        now = datetime.now(timezone.utc)
        await svc.log(action="old", entity_type="t")
        logs_before, _ = await svc.list_logs(since=now + timedelta(hours=1))
        assert logs_before == []

    async def test_pagination(self, session):
        svc = AuditService(session)
        for i in range(5):
            await svc.log(action=f"a{i}", entity_type="t")
        page1, total = await svc.list_logs(limit=2, offset=0)
        assert len(page1) == 2
        assert total == 5
        page2, _ = await svc.list_logs(limit=2, offset=2)
        assert len(page2) == 2


@pytest.mark.asyncio
class TestGetStats:
    async def test_empty_stats(self, session):
        svc = AuditService(session)
        stats = await svc.get_stats()
        assert stats["total_events"] == 0
        assert stats["by_category"] == {}
        assert stats["by_severity"] == {}

    async def test_stats_with_data(self, session, user):
        svc = AuditService(session)
        await svc.log(action="a1", entity_type="t", user_id=user.id, category="api_call", severity="info")
        await svc.log(action="a2", entity_type="t", user_id=user.id, category="api_call", severity="warning")
        await svc.log(action="a3", entity_type="t", user_id=user.id, category="user_action", severity="info")
        stats = await svc.get_stats(user_id=user.id)
        assert stats["total_events"] == 3
        assert stats["by_category"]["api_call"] == 2
        assert stats["by_category"]["user_action"] == 1
        assert stats["by_severity"]["info"] == 2
        assert stats["by_severity"]["warning"] == 1

    async def test_stats_filter_by_category(self, session):
        svc = AuditService(session)
        await svc.log(action="a1", entity_type="t", category="api_call")
        await svc.log(action="a2", entity_type="t", category="user_action")
        stats = await svc.get_stats(category="api_call")
        assert stats["total_events"] == 1
