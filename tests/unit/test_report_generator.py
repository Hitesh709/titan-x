import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.order import OrderFill
from titan_x.models.portfolio import Portfolio, PortfolioHolding
from titan_x.models.user import User
from titan_x.services.report_generator import ReportGenerator


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    u = User(email="report@test.com", hashed_password="hash")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> ReportGenerator:
    return ReportGenerator(session)


class TestPortfolioReport:
    @pytest.mark.asyncio
    async def test_report_not_found(self, svc: ReportGenerator):
        with pytest.raises(ValueError, match="Portfolio not found"):
            await svc.generate_portfolio_report(9999)

    @pytest.mark.asyncio
    async def test_report_empty(self, svc: ReportGenerator, session: AsyncSession):
        p = Portfolio(name="Test")
        session.add(p)
        await session.flush()
        html = await svc.generate_portfolio_report(p.id)
        assert "Test" in html
        assert "Total Value" in html
        assert "Holdings" in html

    @pytest.mark.asyncio
    async def test_report_with_holdings(self, svc: ReportGenerator, session: AsyncSession):
        p = Portfolio(name="My Portfolio")
        session.add(p)
        await session.flush()
        from datetime import date
        h = PortfolioHolding(portfolio_id=p.id, symbol="RELIANCE", quantity=10, average_price=2500, cost_basis=25000, as_of_date=date.today())
        session.add(h)
        await session.flush()
        html = await svc.generate_portfolio_report(p.id)
        assert "RELIANCE" in html
        assert "10" in html


class TestPnlStatement:
    @pytest.mark.asyncio
    async def test_empty(self, svc: ReportGenerator, user: User):
        html = await svc.generate_pnl_statement(user.id)
        assert "P&L Statement" in html
        assert "Open Positions" in html

    @pytest.mark.asyncio
    async def test_with_positions(self, svc: ReportGenerator, user: User, session: AsyncSession):
        from titan_x.models.order import Position
        pos = Position(user_id=user.id, symbol="TCS", quantity=20, average_price=3500, cost_basis=70000, realized_pnl=500, unrealized_pnl=200)
        session.add(pos)
        await session.flush()
        html = await svc.generate_pnl_statement(user.id)
        assert "TCS" in html
        assert "20" in html


class TestTaxReport:
    @pytest.mark.asyncio
    async def test_empty(self, svc: ReportGenerator, user: User):
        html = await svc.generate_tax_report(user.id, 2025)
        assert "Tax Report" in html
        assert "FY 2025" in html

    @pytest.mark.asyncio
    async def test_with_fills(self, svc: ReportGenerator, user: User, session: AsyncSession):
        from titan_x.models.order import Order
        o = Order(user_id=user.id, symbol="TEST", side="sell", order_type="market", quantity=10, status="filled")
        session.add(o)
        await session.flush()
        f = OrderFill(order_id=o.id, symbol="TEST", side="sell", quantity=10, price=100, commission=5, realized_pnl=200)
        session.add(f)
        await session.flush()
        html = await svc.generate_tax_report(user.id, 2025)
        assert "TEST" in html
        assert "$200" in html or "$200.00" in html
