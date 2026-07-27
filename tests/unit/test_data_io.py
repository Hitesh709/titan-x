from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.order import Order, Position
from titan_x.models.price import DailyPrice
from titan_x.models.user import User
from titan_x.services.data_io_service import DataImportExportService
from titan_x.services.order_service import OrderService


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
    u = User(email="io@test.com", hashed_password="hash")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> DataImportExportService:
    return DataImportExportService(session)


# ============================================================
# IMPORT
# ============================================================

class TestImport:
    @pytest.mark.asyncio
    async def test_import_prices(self, svc: DataImportExportService, session: AsyncSession):
        csv_content = "symbol,trade_date,open,high,low,close,volume\nRELIANCE,2025-01-02,100,102,99,101,1000000\nTCS,2025-01-02,200,205,198,203,2000000\n"
        result = await svc.import_daily_prices_csv(csv_content)
        assert result["inserted"] == 2
        assert result["skipped"] == 0

        stmt = select(DailyPrice).where(DailyPrice.symbol == "RELIANCE")
        r = await session.execute(stmt)
        dp = r.scalar_one()
        assert dp.open == 100.0
        assert dp.close == 101.0

    @pytest.mark.asyncio
    async def test_import_prices_skips_duplicates(self, svc: DataImportExportService):
        csv_content = "symbol,trade_date,open,high,low,close,volume\nRELIANCE,2025-01-02,100,102,99,101,1000000\n"
        await svc.import_daily_prices_csv(csv_content)
        result = await svc.import_daily_prices_csv(csv_content)
        assert result["inserted"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_import_prices_skips_missing_fields(self, svc: DataImportExportService):
        csv_content = "symbol,trade_date\nRELIANCE,\n"
        result = await svc.import_daily_prices_csv(csv_content)
        assert result["inserted"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_import_companies(self, svc: DataImportExportService, session: AsyncSession):
        csv_content = "symbol,company_name,isin,sector,exchange\nTCS,Tata Consultancy,IN123456,NSE,Technology\n"
        result = await svc.import_companies_csv(csv_content)
        assert result["inserted"] == 1
        assert result["skipped"] == 0

        stmt = select(Company).where(Company.symbol == "TCS")
        r = await session.execute(stmt)
        c = r.scalar_one()
        assert c.company_name == "Tata Consultancy"

    @pytest.mark.asyncio
    async def test_import_companies_skips_duplicates(self, svc: DataImportExportService):
        csv_content = "symbol,company_name\nTCS,Tata\n"
        await svc.import_companies_csv(csv_content)
        result = await svc.import_companies_csv(csv_content)
        assert result["inserted"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_import_companies_empty_symbol(self, svc: DataImportExportService):
        csv_content = "symbol,company_name\n,\n"
        result = await svc.import_companies_csv(csv_content)
        assert result["inserted"] == 0
        assert result["skipped"] == 1


# ============================================================
# EXPORT
# ============================================================

class TestExport:
    @pytest.mark.asyncio
    async def test_export_prices_empty(self, svc: DataImportExportService):
        csv = await svc.export_daily_prices_csv("NONEXISTENT")
        lines = csv.strip().split("\n")
        assert len(lines) == 1
        assert "symbol" in lines[0]

    @pytest.mark.asyncio
    async def test_export_prices(self, svc: DataImportExportService):
        csv_content = "symbol,trade_date,open,high,low,close,volume\nRELIANCE,2025-01-02,100,102,99,101,1000000\n"
        await svc.import_daily_prices_csv(csv_content)
        csv_out = await svc.export_daily_prices_csv("RELIANCE")
        lines = csv_out.strip().split("\n")
        assert len(lines) == 2
        assert "RELIANCE" in lines[1]

    @pytest.mark.asyncio
    async def test_export_prices_with_date_range(self, svc: DataImportExportService):
        csv_in = "symbol,trade_date,open,high,low,close,volume\nRELIANCE,2025-01-01,99,101,98,100,900000\nRELIANCE,2025-01-02,100,102,99,101,1000000\nRELIANCE,2025-01-03,101,103,100,102,1100000\n"
        await svc.import_daily_prices_csv(csv_in)
        csv_out = await svc.export_daily_prices_csv("RELIANCE", start=date(2025, 1, 2), end=date(2025, 1, 2))
        lines = csv_out.strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_export_positions(self, svc: DataImportExportService, user: User, session: AsyncSession):
        pos = Position(
            user_id=user.id, symbol="TEST", quantity=50,
            average_price=100, cost_basis=5000, realized_pnl=200, unrealized_pnl=50,
        )
        session.add(pos)
        await session.flush()

        csv_out = await svc.export_positions_csv(user.id)
        lines = csv_out.strip().split("\n")
        assert len(lines) == 2
        assert "TEST" in lines[1]
        assert "50" in lines[1]

    @pytest.mark.asyncio
    async def test_export_positions_empty(self, svc: DataImportExportService, user: User):
        csv_out = await svc.export_positions_csv(user.id)
        lines = csv_out.strip().split("\n")
        assert len(lines) == 1

    @pytest.mark.asyncio
    async def test_export_orders(self, svc: DataImportExportService, user: User, session: AsyncSession):
        o = Order(user_id=user.id, symbol="TEST", side="buy", order_type="market", quantity=10)
        session.add(o)
        await session.flush()

        csv_out = await svc.export_orders_csv(user.id)
        lines = csv_out.strip().split("\n")
        assert len(lines) == 2
        assert "TEST" in lines[1]
        assert "buy" in lines[1]

    @pytest.mark.asyncio
    async def test_export_orders_empty(self, svc: DataImportExportService, user: User):
        csv_out = await svc.export_orders_csv(user.id)
        lines = csv_out.strip().split("\n")
        assert len(lines) == 1
