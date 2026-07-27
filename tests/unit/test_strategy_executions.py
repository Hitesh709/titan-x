import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.price import DailyPrice
from titan_x.models.strategy import Strategy, StrategyExecution
from titan_x.models.user import User
from titan_x.services.strategy_execution_service import StrategyExecutionService

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
        s.add_all([u1, u2])
        await s.commit()
        yield {"alice": u1, "bob": u2}
        await s.close()


@pytest_asyncio.fixture
async def session(engine, users):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def seeded_session(session, users):
    today = date.today()
    month_ago = today - timedelta(days=30)

    for sym, name, sector in [
        ("AAPL", "Apple Inc", "Technology"),
        ("MSFT", "Microsoft Corp", "Technology"),
        ("JPM", "JPMorgan Chase", "Financials"),
        ("XOM", "Exxon Mobil", "Energy"),
    ]:
        session.add(Company(symbol=sym, company_name=name, sector=sector, industry=sector, exchange="NASDAQ", market_cap=1_000_000_000, isin=f"US{sym}01", status="active"))

    for sym, close in [("AAPL", 200), ("MSFT", 350), ("JPM", 180), ("XOM", 120)]:
        session.add(DailyPrice(symbol=sym, trade_date=month_ago, open=close, high=close, low=close, close=close, volume=1_000_000))
        session.add(DailyPrice(symbol=sym, trade_date=today, open=close, high=close, low=close, close=close, volume=2_000_000))

    for sym, score in [("AAPL", 75), ("MSFT", 68), ("JPM", 55), ("XOM", 35)]:
        session.add(DynamicAIScore(symbol=sym, as_of_date=today, combined_score=score, combined_signal="bullish", combined_confidence=70, technical_score=50, fundamental_score=50, news_score=50, macro_score=50, liquidity_score=50, risk_score=50, market_regime_score=50))

    alice_id = users["alice"].id
    session.add(Strategy(user_id=alice_id, name="Tech Scan", filters_json=json.dumps({"sector": "Technology"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]"))
    session.add(Strategy(user_id=alice_id, name="Energy Scan", filters_json=json.dumps({"sector": "Energy"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]"))
    session.add(Strategy(user_id=alice_id, name="No Filters", filters_json="{}", entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]"))
    session.add(Strategy(user_id=alice_id, name="Scheduled", filters_json=json.dumps({"sector": "Financials"}), entry_criteria_json="[]", exit_criteria_json="[]", risk_rules_json="{}", position_rules_json="{}", tags_json="[]", schedule_cron="*/5 * * * *", schedule_enabled=True))

    await session.commit()
    return session


# ── Execute single ──

@pytest.mark.asyncio
class TestExecuteSingle:
    async def test_execute_manual(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        result = await svc.execute_strategy(s.id, users["alice"].id)
        assert result is not None
        assert result["status"] == "completed"
        assert result["total_results"] == 2
        assert result["execution_type"] == "manual"
        assert result["execution_time_ms"] is not None

    async def test_execute_stores_results(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        result = await svc.execute_strategy(s.id, users["alice"].id)
        assert result["results"] is not None
        assert len(result["results"]) == 2
        symbols = {r["symbol"] for r in result["results"]}
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    async def test_execute_no_filters(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "No Filters")
        )).scalar_one()
        result = await svc.execute_strategy(s.id, users["alice"].id)
        assert result["status"] == "completed"
        assert result["total_results"] >= 0

    async def test_execute_not_found(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        result = await svc.execute_strategy(9999, users["alice"].id)
        assert result is None

    async def test_execute_private_no_access(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        result = await svc.execute_strategy(s.id, users["bob"].id)
        assert result is None

    async def test_execute_updates_strategy(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        await svc.execute_strategy(s.id, users["alice"].id)
        await seeded_session.refresh(s)
        assert s.last_results_count == 2
        assert s.last_run_at is not None


# ── Historical Replay ──

@pytest.mark.asyncio
class TestHistoricalReplay:
    async def test_execute_with_as_of_date(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        past = date.today() - timedelta(days=1)
        result = await svc.execute_strategy(s.id, users["alice"].id, as_of_date=past)
        assert result is not None
        assert result["as_of_date"] == past.isoformat()
        assert result["status"] == "completed"

    async def test_execute_replay_different_date(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Energy Scan")
        )).scalar_one()
        old = date.today() - timedelta(days=60)
        result = await svc.execute_strategy(s.id, users["alice"].id, as_of_date=old)
        assert result["status"] == "completed"


# ── Batch ──

@pytest.mark.asyncio
class TestBatch:
    async def test_execute_batch(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        alice = users["alice"].id
        s1 = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        s2 = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Energy Scan")
        )).scalar_one()
        results = await svc.execute_batch([s1.id, s2.id], alice)
        assert len(results) == 2
        assert all(r["status"] == "completed" for r in results)
        assert results[0]["batch_id"] == results[1]["batch_id"]
        assert results[0]["execution_type"] == "batch"

    async def test_batch_partial_failure(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        alice = users["alice"].id
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        results = await svc.execute_batch([s.id, 9999], alice)
        assert len(results) == 1

    async def test_batch_with_as_of_date(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        alice = users["alice"].id
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        past = date.today() - timedelta(days=5)
        results = await svc.execute_batch([s.id], alice, as_of_date=past)
        assert results[0]["as_of_date"] == past.isoformat()


# ── Scheduled ──

@pytest.mark.asyncio
class TestScheduled:
    async def test_execute_scheduled(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        results = await svc.execute_scheduled()
        for r in results:
            assert r["status"] == "completed"
            assert r["execution_type"] == "scheduled"

    async def test_scheduled_runs_due_strategies(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        results = await svc.execute_scheduled()
        strategy_ids = {r["strategy_id"] for r in results}
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Scheduled")
        )).scalar_one()
        assert s.id in strategy_ids

    async def test_scheduled_skips_disabled(self, session, users):
        svc = StrategyExecutionService(session)
        results = await svc.execute_scheduled()
        assert results == []


# ── Get Executions ──

@pytest.mark.asyncio
class TestGetExecutions:
    async def test_get_executions(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        await svc.execute_strategy(s.id, users["alice"].id)
        await svc.execute_strategy(s.id, users["alice"].id)
        rows, total = await svc.get_executions(s.id, users["alice"].id)
        assert total == 2
        assert len(rows) == 2

    async def test_get_executions_private_no_access(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        rows, total = await svc.get_executions(s.id, users["bob"].id)
        assert total == 0
        assert rows == []

    async def test_get_execution_detail(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        exec_result = await svc.execute_strategy(s.id, users["alice"].id)
        detail = await svc.get_execution(exec_result["id"], users["alice"].id)
        assert detail is not None
        assert detail["id"] == exec_result["id"]
        assert detail["total_results"] == 2
        assert detail["results"] is not None

    async def test_get_execution_not_found(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        detail = await svc.get_execution(9999, users["alice"].id)
        assert detail is None

    async def test_get_batch_executions(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        alice = users["alice"].id
        s1 = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        s2 = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Energy Scan")
        )).scalar_one()
        batch_results = await svc.execute_batch([s1.id, s2.id], alice)
        batch_id = batch_results[0]["batch_id"]
        batch = await svc.get_batch_executions(batch_id, alice)
        assert len(batch) == 2
        assert all(b["batch_id"] == batch_id for b in batch)

    async def test_get_batch_nonexistent(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        batch = await svc.get_batch_executions("nonexistent-batch", users["alice"].id)
        assert batch == []

    async def test_get_executions_pagination(self, seeded_session, users):
        svc = StrategyExecutionService(seeded_session)
        s = (await seeded_session.execute(
            select(Strategy).where(Strategy.name == "Tech Scan")
        )).scalar_one()
        for _ in range(5):
            await svc.execute_strategy(s.id, users["alice"].id)
        rows, total = await svc.get_executions(s.id, users["alice"].id, skip=0, limit=2)
        assert total == 5
        assert len(rows) == 2
