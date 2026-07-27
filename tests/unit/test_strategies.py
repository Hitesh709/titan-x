import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.price import DailyPrice
from titan_x.models.strategy import Strategy, StrategyShare
from titan_x.models.user import User
from titan_x.services.strategy_service import StrategyService

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
async def users(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        u1 = User(email="alice@test.com", hashed_password="pw")
        u2 = User(email="bob@test.com", hashed_password="pw")
        u3 = User(email="charlie@test.com", hashed_password="pw")
        s.add_all([u1, u2, u3])
        await s.commit()
        yield {"alice": u1, "bob": u2, "charlie": u3}
        await s.close()


@pytest_asyncio.fixture
async def session(engine, users):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def seeded_session(session, users):
    today = date.today()
    month_ago = today - timedelta(days=30)

    companies = {
        "AAPL": ("Apple Inc", "Technology"),
        "MSFT": ("Microsoft Corp", "Technology"),
        "JPM": ("JPMorgan Chase", "Financials"),
        "XOM": ("Exxon Mobil", "Energy"),
    }
    for sym, (name, sector) in companies.items():
        session.add(Company(symbol=sym, company_name=name, sector=sector, industry=sector, exchange="NASDAQ", market_cap=1_000_000_000, isin=f"US{sym}01", status="active"))

    for sym, close in [("AAPL", 200), ("MSFT", 350), ("JPM", 180), ("XOM", 120)]:
        session.add(DailyPrice(symbol=sym, trade_date=month_ago, open=close, high=close, low=close, close=close, volume=1_000_000))
        session.add(DailyPrice(symbol=sym, trade_date=today, open=close, high=close, low=close, close=close, volume=2_000_000))

    for sym, score in [("AAPL", 75), ("MSFT", 68), ("JPM", 55), ("XOM", 35)]:
        session.add(DynamicAIScore(symbol=sym, as_of_date=today, combined_score=score, combined_signal="bullish", combined_confidence=70, technical_score=50, fundamental_score=50, news_score=50, macro_score=50, liquidity_score=50, risk_score=50, market_regime_score=50))

    await session.commit()
    return session


# ── Helper ──

class TestHelpers:
    @pytest.mark.asyncio
    async def test_to_dict_roundtrip(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Test", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        d = svc._to_dict(s)
        assert d["name"] == "Test"
        assert d["id"] == s.id
        assert d["is_public"] is False
        assert d["cloned_from_id"] is None


# ── Create / Get ──

@pytest.mark.asyncio
class TestCreateAndGet:
    async def test_create_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(
            user_id=1, name="My Strategy",
            description="A test strategy",
            entry_criteria_json="[]", exit_criteria_json="[]",
            risk_rules_json="{}", position_rules_json="{}",
            filters_json=json.dumps({"sector": "Technology"}),
            tags_json="[]",
        )
        assert s.id is not None
        assert s.name == "My Strategy"
        assert s.filters_json == '{"sector": "Technology"}'

    async def test_get_own_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.get_strategy(s.id, user_id=1)
        assert result is not None
        assert result["name"] == "X"

    async def test_get_private_strategy_wrong_user(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.get_strategy(s.id, user_id=2)
        assert result is None

    async def test_get_public_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", is_public=True, entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.get_strategy(s.id, user_id=2)
        assert result is not None

    async def test_get_shared_strategy(self, session, users):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=2)
        result = await svc.get_strategy(s.id, user_id=2)
        assert result is not None


# ── Update ──

@pytest.mark.asyncio
class TestUpdate:
    async def test_update_own_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Old", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.update_strategy(s.id, user_id=1, name="New", is_public=True)
        assert result is not None
        assert result["name"] == "New"
        assert result["is_public"] is True

    async def test_update_not_owner(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Old", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.update_strategy(s.id, user_id=2, name="New")
        assert result is None

    async def test_update_filters(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.update_strategy(s.id, user_id=1, filters={"sector": "Energy", "fundamental": {"pe_ratio": {"max": 15}}})
        assert result is not None
        assert json.loads(result["filters_json"])["sector"] == "Energy"

    async def test_update_version_increments(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        v1 = s.version
        result = await svc.update_strategy(s.id, user_id=1, name="Y")
        assert result["version"] == v1 + 1


# ── Delete ──

@pytest.mark.asyncio
class TestDelete:
    async def test_delete_own(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        ok = await svc.delete_strategy(s.id, user_id=1)
        assert ok
        assert await svc.get_strategy(s.id, user_id=1) is None

    async def test_delete_not_owner(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        ok = await svc.delete_strategy(s.id, user_id=2)
        assert not ok
        assert await svc.get_strategy(s.id, user_id=1) is not None

    async def test_delete_not_found(self, session):
        svc = StrategyService(session)
        ok = await svc.delete_strategy(9999, user_id=1)
        assert not ok


# ── Clone ──

@pytest.mark.asyncio
class TestClone:
    async def test_clone_own_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Original", description="desc", filters_json=json.dumps({"sector": "Tech"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json='["tag1"]')
        cloned = await svc.clone_strategy(s.id, user_id=1)
        assert cloned is not None
        assert cloned["name"] == "Original (clone)"
        assert cloned["cloned_from_id"] == s.id
        assert cloned["user_id"] == 1
        assert cloned["description"] == "desc"
        assert json.loads(cloned["filters_json"])["sector"] == "Tech"

    async def test_clone_public_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Public", is_public=True, entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        cloned = await svc.clone_strategy(s.id, user_id=2)
        assert cloned is not None
        assert cloned["user_id"] == 2

    async def test_clone_private_not_owner(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Private", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        cloned = await svc.clone_strategy(s.id, user_id=2)
        assert cloned is None

    async def test_clone_not_found(self, session):
        svc = StrategyService(session)
        cloned = await svc.clone_strategy(9999, user_id=1)
        assert cloned is None

    async def test_clone_with_custom_name(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Original", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        cloned = await svc.clone_strategy(s.id, user_id=1, new_name="My Copy")
        assert cloned["name"] == "My Copy"

    async def test_clone_shared_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Shared", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=2)
        cloned = await svc.clone_strategy(s.id, user_id=2)
        assert cloned is not None
        assert cloned["user_id"] == 2


# ── Share ──

@pytest.mark.asyncio
class TestShare:
    async def test_share_strategy(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.share_strategy(s.id, owner_id=1, target_user_id=2, permission="run")
        assert result is not None
        assert result["shared_with_user_id"] == 2
        assert result["permission"] == "run"

    async def test_share_self_not_allowed(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.share_strategy(s.id, owner_id=1, target_user_id=1)
        assert result is None

    async def test_share_not_owner(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.share_strategy(s.id, owner_id=2, target_user_id=3)
        assert result is None

    async def test_unshare(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=2)
        ok = await svc.unshare_strategy(s.id, owner_id=1, target_user_id=2)
        assert ok
        result = await svc.get_strategy(s.id, user_id=2)
        assert result is None

    async def test_unshare_not_owner(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        ok = await svc.unshare_strategy(s.id, owner_id=2, target_user_id=1)
        assert not ok

    async def test_list_shares(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=2, permission="view")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=3, permission="edit")
        shares = await svc.list_shares(s.id, owner_id=1)
        assert len(shares) == 2
        uids = [s["shared_with_user_id"] for s in shares]
        assert 2 in uids
        assert 3 in uids

    async def test_list_shares_not_owner(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        shares = await svc.list_shares(s.id, owner_id=2)
        assert shares == []

    async def test_update_share_permission(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=2, permission="view")
        result = await svc.share_strategy(s.id, owner_id=1, target_user_id=2, permission="edit")
        assert result["permission"] == "edit"


# ── Run ──

@pytest.mark.asyncio
class TestRun:
    async def test_run_strategy_with_filters(self, seeded_session, users):
        svc = StrategyService(seeded_session)
        filters = json.dumps({"sector": "Technology"})
        s = await svc._repo.create(user_id=1, name="Tech Scan", filters_json=filters, entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.run_strategy(s.id, user_id=1)
        assert result is not None
        assert result["total"] == 2
        symbols = {r["symbol"] for r in result["results"]}
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    async def test_run_strategy_no_filters(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Empty", filters_json="{}", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.run_strategy(s.id, user_id=1)
        assert result is not None
        assert result["total"] == 0

    async def test_run_strategy_no_filters_column(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="No Filters", filters_json=None, entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.run_strategy(s.id, user_id=1)
        assert result is not None
        assert result["total"] == 0

    async def test_run_updates_last_run(self, seeded_session):
        svc = StrategyService(seeded_session)
        s = await svc._repo.create(user_id=1, name="S", filters_json=json.dumps({"sector": "Energy"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.run_strategy(s.id, user_id=1)
        fresh = await svc._repo.get(s.id)
        assert fresh.last_results_count == 1
        assert fresh.last_run_at is not None

    async def test_run_public_strategy(self, seeded_session):
        svc = StrategyService(seeded_session)
        s = await svc._repo.create(user_id=1, name="Public Scan", is_public=True, filters_json=json.dumps({"sector": "Technology"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.run_strategy(s.id, user_id=2)
        assert result is not None
        assert result["total"] == 2

    async def test_run_shared_strategy(self, seeded_session):
        svc = StrategyService(seeded_session)
        s = await svc._repo.create(user_id=1, name="Shared Scan", filters_json=json.dumps({"sector": "Technology"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=2)
        result = await svc.run_strategy(s.id, user_id=2)
        assert result is not None
        assert result["total"] == 2

    async def test_run_not_found(self, session):
        svc = StrategyService(session)
        result = await svc.run_strategy(9999, user_id=1)
        assert result is None

    async def test_run_private_no_access(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Private", filters_json=json.dumps({"sector": "Tech"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.run_strategy(s.id, user_id=2)
        assert result is None


# ── Schedule ──

@pytest.mark.asyncio
class TestSchedule:
    async def test_set_schedule(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.set_schedule(s.id, user_id=1, cron="0 9 * * 1-5", enabled=True)
        assert result is not None
        assert result["schedule_cron"] == "0 9 * * 1-5"
        assert result["schedule_enabled"] is True

    async def test_disable_schedule(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.set_schedule(s.id, user_id=1, cron="0 9 * * 1-5", enabled=True)
        result = await svc.set_schedule(s.id, user_id=1, cron=None, enabled=False)
        assert result["schedule_cron"] is None
        assert result["schedule_enabled"] is False

    async def test_set_schedule_not_owner(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="X", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        result = await svc.set_schedule(s.id, user_id=2, cron="0 9 * * 1-5")
        assert result is None

    async def test_set_schedule_not_found(self, session):
        svc = StrategyService(session)
        result = await svc.set_schedule(9999, user_id=1, cron="0 9 * * 1-5")
        assert result is None


# ── List ──

@pytest.mark.asyncio
class TestList:
    async def test_list_own_strategies(self, session):
        svc = StrategyService(session)
        await svc._repo.create(user_id=1, name="A", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc._repo.create(user_id=1, name="B", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc._repo.create(user_id=2, name="C", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        rows, total = await svc.list_user_strategies(user_id=1)
        assert total == 2

    async def test_list_includes_shared(self, session):
        svc = StrategyService(session)
        s = await svc._repo.create(user_id=1, name="Shared With Bob", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        await svc.share_strategy(s.id, owner_id=1, target_user_id=2)
        rows, total = await svc.list_user_strategies(user_id=2)
        assert total == 1

    async def test_list_includes_public(self, session):
        svc = StrategyService(session)
        await svc._repo.create(user_id=1, name="Public", is_public=True, entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        rows, total = await svc.list_user_strategies(user_id=2)
        assert total == 1

    async def test_list_without_public(self, session):
        svc = StrategyService(session)
        await svc._repo.create(user_id=1, name="Public", is_public=True, entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        rows, total = await svc.list_user_strategies(user_id=2, include_public=False)
        assert total == 0

    async def test_list_pagination(self, session):
        svc = StrategyService(session)
        for i in range(5):
            await svc._repo.create(user_id=1, name=f"S{i}", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]")
        rows, total = await svc.list_user_strategies(user_id=1, skip=0, limit=2)
        assert total == 5
        assert len(rows) == 2
