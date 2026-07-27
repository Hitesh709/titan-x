from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.portfolio import Portfolio, PortfolioHolding
from titan_x.models.portfolio_optimizer import OptimizationAllocation, PortfolioOptimization
from titan_x.models.price import DailyPrice
from titan_x.models.sector import SectorPerformance
from titan_x.services.portfolio_optimizer_service import PortfolioOptimizerService

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
async def session(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def service(session):
    return PortfolioOptimizerService(session)


@pytest_asyncio.fixture
async def seed_portfolio(session):
    today = date.today()
    c1 = Company(symbol="AAPL", company_name="Apple Inc", isin="US0378331005",
                 sector="Technology", exchange="NASDAQ", status="active")
    c2 = Company(symbol="JNJ", company_name="J&J", isin="US4781601046",
                 sector="Healthcare", exchange="NYSE", status="active")
    c3 = Company(symbol="MSFT", company_name="Microsoft", isin="US5949181045",
                 sector="Technology", exchange="NASDAQ", status="active")
    session.add_all([c1, c2, c3])

    sp1 = SectorPerformance(sector="Technology", as_of_date=today,
                            period_label="1M", return_pct=5.0)
    sp2 = SectorPerformance(sector="Healthcare", as_of_date=today,
                            period_label="1M", return_pct=2.0)
    session.add_all([sp1, sp2])

    for sym in ["AAPL", "JNJ", "MSFT"]:
        for i in range(100):
            dp = DailyPrice(symbol=sym, trade_date=today - timedelta(days=(99 - i)),
                            open=100 + i, high=101 + i, low=99 + i,
                            close=100 + i, volume=1_000_000)
            session.add(dp)

    pf = Portfolio(name="Test Portfolio", description="Test")
    session.add(pf)
    await session.flush()

    holdings = [
        PortfolioHolding(portfolio_id=pf.id, symbol="AAPL", sector="Technology",
                         quantity=100, average_price=150, cost_basis=15000,
                         as_of_date=today),
        PortfolioHolding(portfolio_id=pf.id, symbol="JNJ", sector="Healthcare",
                         quantity=200, average_price=100, cost_basis=20000,
                         as_of_date=today),
        PortfolioHolding(portfolio_id=pf.id, symbol="MSFT", sector="Technology",
                         quantity=50, average_price=200, cost_basis=10000,
                         as_of_date=today),
    ]
    session.add_all(holdings)
    await session.flush()
    return pf.id


class TestOptimize:
    async def test_optimize_equal_weight(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "equal_weight")
        assert opt.strategy == "equal_weight"
        assert opt.total_holdings > 0
        assert opt.expected_return is not None

    async def test_optimize_risk_parity(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "risk_parity")
        assert opt.strategy == "risk_parity"
        assert opt.expected_volatility is not None

    async def test_optimize_max_sharpe(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "max_sharpe")
        assert opt.strategy == "max_sharpe"

    async def test_optimize_sector_balanced(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "sector_balanced")
        assert opt.strategy == "sector_balanced"

    async def test_optimize_invalid_portfolio(self, service):
        with pytest.raises(ValueError, match="Portfolio 9999 not found"):
            await service.optimize(9999)

    async def test_optimize_generates_report(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "risk_parity")
        assert opt.report_json is not None
        import json
        report = json.loads(opt.report_json)
        assert "summary" in report
        assert "scores" in report
        assert "recommendations" in report

    async def test_optimize_sets_scores(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "risk_parity")
        assert opt.diversification_score is not None
        assert opt.risk_score is not None
        assert opt.sector_balance_score is not None


class TestAllocations:
    async def test_allocations_created(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "risk_parity")
        allocs = await service.get_allocations(opt.id)
        assert len(allocs) > 0
        total_pct = sum(a.allocation_pct for a in allocs)
        assert abs(total_pct - 100.0) < 1.0

    async def test_allocations_have_expected_metrics(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio, "risk_parity")
        allocs = await service.get_allocations(opt.id)
        for a in allocs:
            assert a.symbol is not None
            assert a.allocation_pct > 0
            assert a.expected_return is not None
            assert a.expected_risk is not None
            assert a.rank > 0


class TestHistory:
    async def test_get_optimization(self, service, seed_portfolio):
        opt = await service.optimize(seed_portfolio)
        found = await service.get_optimization(opt.id)
        assert found is not None
        assert found.id == opt.id

    async def test_get_optimization_not_found(self, service):
        found = await service.get_optimization(9999)
        assert found is None

    async def test_get_history(self, service, seed_portfolio):
        await service.optimize(seed_portfolio)
        history = await service.get_history(seed_portfolio)
        assert len(history) > 0


class TestHelpers:
    def test_diversification_score(self, service):
        allocs = [
            {"allocation_pct": 50.0, "symbol": "A"},
            {"allocation_pct": 30.0, "symbol": "B"},
            {"allocation_pct": 20.0, "symbol": "C"},
        ]
        score = service._diversification_score(allocs)
        assert 0 < score <= 100

    def test_diversification_score_concentrated(self, service):
        allocs = [{"allocation_pct": 100.0, "symbol": "A"}]
        score = service._diversification_score(allocs)
        assert score == 0

    def test_sector_balance_score(self, service):
        allocs = [
            {"allocation_pct": 50.0, "symbol": "A", "sector": "Tech"},
            {"allocation_pct": 50.0, "symbol": "B", "sector": "Health"},
        ]
        score = service._sector_balance_score(allocs)
        assert 0 < score <= 100

    def test_risk_score(self, service):
        score = service._risk_score(0.2, [], {})
        assert 0 <= score <= 100
