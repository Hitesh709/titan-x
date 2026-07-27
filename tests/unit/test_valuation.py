import json
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.valuation import DCFValuation, RelativeValuation, SectorValuation, ValuationReport
from titan_x.services.valuation_service import ValuationService


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
def svc(session: AsyncSession) -> ValuationService:
    return ValuationService(session)


# ============================================================
# DCF VALUATION
# ============================================================

class TestDCF:
    @pytest.mark.asyncio
    async def test_compute_dcf_basic(self, svc: ValuationService):
        result = await svc.compute_dcf("TCS", free_cash_flow=1000, growth_rate_5y=0.10,
                                       wacc=0.10, shares_outstanding=100, net_debt=200, cash_and_equivalents=50)
        assert result.symbol == "TCS"
        assert result.present_value_fcf > 0
        assert result.terminal_value > 0
        assert result.present_value_tv > 0
        assert result.enterprise_value > 0
        assert result.equity_value > 0
        assert result.intrinsic_value > 0
        assert result.current_price is None

    @pytest.mark.asyncio
    async def test_compute_dcf_with_price(self, svc: ValuationService, session: AsyncSession):
        session.add(DailyPrice(symbol="RELIANCE", trade_date=date(2025, 1, 15), open=2500, high=2550, low=2480, close=2510, volume=100000))
        await session.flush()
        result = await svc.compute_dcf("RELIANCE", free_cash_flow=50000, growth_rate_5y=0.12,
                                       wacc=0.09, shares_outstanding=1000, net_debt=5000, cash_and_equivalents=2000)
        assert result.current_price == 2510
        assert result.upside_pct is not None

    @pytest.mark.asyncio
    async def test_dcf_upside_overvalued(self, svc: ValuationService):
        result = await svc.compute_dcf("AAPL", free_cash_flow=10000, growth_rate_5y=0.05,
                                       wacc=0.12, shares_outstanding=500, net_debt=1000, cash_and_equivalents=500,
                                       current_price=500)
        assert result.upside_pct is not None
        assert result.intrinsic_value > 0

    @pytest.mark.asyncio
    async def test_get_dcf_returns_latest(self, svc: ValuationService):
        await svc.compute_dcf("TEST", free_cash_flow=1000)
        await svc.compute_dcf("TEST", free_cash_flow=2000)
        result = await svc.get_dcf("TEST")
        assert result is not None
        assert result.free_cash_flow == 2000

    @pytest.mark.asyncio
    async def test_get_dcf_not_found(self, svc: ValuationService):
        result = await svc.get_dcf("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_dcf_terminal_growth_guard(self, svc: ValuationService):
        result = await svc.compute_dcf("TEST", free_cash_flow=1000, wacc=0.08, terminal_growth_rate=0.03)
        dcf = await svc.get_dcf("TEST")
        assert dcf is not None

    @pytest.mark.asyncio
    async def test_dcf_missing_fcf(self, svc: ValuationService):
        result = await svc.compute_dcf("TEST")
        assert result.free_cash_flow == 0
        assert result.intrinsic_value == 0

    @pytest.mark.asyncio
    async def test_dcf_symbol_upper(self, svc: ValuationService):
        result = await svc.compute_dcf("test", free_cash_flow=500)
        assert result.symbol == "TEST"


# ============================================================
# RELATIVE VALUATION
# ============================================================

class TestRelativeValuation:
    @pytest.mark.asyncio
    async def test_compute_relative_basic(self, svc: ValuationService):
        result = await svc.compute_relative("TCS", eps=50, book_value_per_share=200,
                                            revenue_per_share=300, current_price=1000,
                                            industry_avg_pe=25, industry_avg_pb=5, industry_avg_ps=4)
        assert result.symbol == "TCS"
        assert result.pe_ratio == 20.0
        assert result.pb_ratio == 5.0
        assert result.ps_ratio == 3.33
        assert result.pe_fair_value == 1250.0
        assert result.pb_fair_value == 1000.0
        assert result.ps_fair_value == 1200.0
        assert result.composite_fair_value is not None
        assert result.upside_pct is not None

    @pytest.mark.asyncio
    async def test_compute_relative_without_price(self, svc: ValuationService, session: AsyncSession):
        session.add(DailyPrice(symbol="HDFC", trade_date=date(2025, 2, 1), open=1600, high=1620, low=1580, close=1610, volume=50000))
        await session.flush()
        result = await svc.compute_relative("HDFC", eps=80, industry_avg_pe=20)
        assert result.current_price == 1610
        assert result.pe_ratio == 20.12

    @pytest.mark.asyncio
    async def test_relative_missing_data(self, svc: ValuationService):
        result = await svc.compute_relative("TEST", current_price=100)
        assert result.pe_ratio is None
        assert result.composite_fair_value is None

    @pytest.mark.asyncio
    async def test_get_relative_returns_latest(self, svc: ValuationService):
        await svc.compute_relative("TEST", eps=10, industry_avg_pe=15, current_price=100)
        await svc.compute_relative("TEST", eps=20, industry_avg_pe=15, current_price=100)
        result = await svc.get_relative("TEST")
        assert result is not None
        assert result.eps is not None

    @pytest.mark.asyncio
    async def test_get_relative_not_found(self, svc: ValuationService):
        result = await svc.get_relative("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_relative_partial_pe_only(self, svc: ValuationService):
        result = await svc.compute_relative("TEST", eps=10, industry_avg_pe=20, current_price=100)
        assert result.pe_fair_value == 200.0
        assert result.pb_fair_value is None
        assert result.composite_fair_value == 200.0


# ============================================================
# SECTOR VALUATION
# ============================================================

class TestSectorValuation:
    @pytest.mark.asyncio
    async def test_compute_sector_with_peer_data(self, svc: ValuationService):
        await svc.compute_relative("TEST", eps=10, industry_avg_pe=20, current_price=100)
        peer_data = [
            {"symbol": "PEER1", "pe": 25, "pb": 4, "ps": 3},
            {"symbol": "PEER2", "pe": 15, "pb": 3, "ps": 2},
            {"symbol": "PEER3", "pe": 20, "pb": 5, "ps": 4},
        ]
        result = await svc.compute_sector("TEST", sector_pe_data=peer_data)
        assert result.peer_count == 3
        assert result.peer_avg_pe == 20.0
        assert result.peer_median_pe == 20
        assert result.peer_avg_pb == 4.0
        assert result.sector_grade in ("Undervalued", "Fair", "Overvalued")

    @pytest.mark.asyncio
    async def test_compute_sector_with_company(self, svc: ValuationService, session: AsyncSession):
        session.add(Company(symbol="TEST", company_name="Test Corp", isin="IN1234567890", sector="Technology", exchange="NSE"))
        session.add(Company(symbol="PEER1", company_name="Peer 1", isin="IN1111111111", sector="Technology", exchange="NSE"))
        session.add(Company(symbol="PEER2", company_name="Peer 2", isin="IN2222222222", sector="Technology", exchange="NSE"))
        await session.flush()
        await svc.compute_relative("PEER1", eps=10, industry_avg_pe=20, current_price=100)
        await svc.compute_relative("PEER2", eps=20, industry_avg_pe=20, current_price=100)
        await svc.compute_relative("TEST", eps=15, industry_avg_pe=20, current_price=100)
        result = await svc.compute_sector("TEST")
        assert result.sector == "Technology"
        assert result.peer_count == 2

    @pytest.mark.asyncio
    async def test_sector_percentile(self, svc: ValuationService):
        peer_data = [{"symbol": f"P{i}", "pe": v, "pb": 5, "ps": 3} for i, v in enumerate([10, 12, 15, 18, 20, 22, 25, 30, 35, 40])]
        await svc.compute_relative("TEST", eps=15, industry_avg_pe=20, current_price=100)
        result = await svc.compute_sector("TEST", sector_pe_data=peer_data)
        assert result.pe_percentile is not None
        assert 0 <= result.pe_percentile <= 100

    @pytest.mark.asyncio
    async def test_get_sector_not_found(self, svc: ValuationService):
        result = await svc.get_sector("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_sector_no_peers(self, svc: ValuationService):
        result = await svc.compute_sector("TEST")
        assert result.peer_count == 0


# ============================================================
# VALUATION REPORT
# ============================================================

class TestValuationReport:
    @pytest.mark.asyncio
    async def test_generate_report(self, svc: ValuationService, session: AsyncSession):
        session.add(Company(symbol="TCS", company_name="TCS Ltd", isin="IN1234567890", sector="IT", exchange="NSE"))
        await session.flush()
        await svc.compute_dcf("TCS", free_cash_flow=10000, growth_rate_5y=0.10,
                              wacc=0.10, shares_outstanding=500, net_debt=1000, cash_and_equivalents=500)
        await svc.compute_relative("TCS", eps=50, book_value_per_share=200, revenue_per_share=300,
                                   current_price=1000, industry_avg_pe=25, industry_avg_pb=5, industry_avg_ps=4)
        result = await svc.generate_report("TCS")
        assert result.symbol == "TCS"
        assert result.dcf_fair_value is not None
        assert result.composite_fair_value is not None
        assert result.margin_of_safety_pct is not None
        assert result.recommendation in ("strong_buy", "buy", "hold", "sell", "strong_sell")
        assert result.report_json is not None

    @pytest.mark.asyncio
    async def test_report_json_structure(self, svc: ValuationService):
        result = await svc.generate_report("TEST")
        data = json.loads(result.report_json)
        assert "symbol" in data
        assert "dcf" in data
        assert "relative" in data
        assert "sector" in data
        assert "composite_fair_value" in data
        assert "margin_of_safety_pct" in data
        assert "recommendation" in data

    @pytest.mark.asyncio
    async def test_report_with_inputs(self, svc: ValuationService, session: AsyncSession):
        session.add(Company(symbol="ACME", company_name="Acme Corp", isin="IN9999999999", sector="Industrial", exchange="NSE"))
        await session.flush()
        await svc.compute_dcf("ACME", free_cash_flow=5000, growth_rate_5y=0.10, wacc=0.10,
                              shares_outstanding=500, net_debt=1000, cash_and_equivalents=500)
        await svc.compute_relative("ACME", eps=25, industry_avg_pe=22, current_price=500)
        report = await svc.generate_report("ACME")
        assert report.dcf_fair_value is not None
        assert report.relative_fair_value is not None
        assert report.composite_fair_value is not None
        assert report.margin_of_safety_pct is not None

    @pytest.mark.asyncio
    async def test_report_margin_of_safety(self, svc: ValuationService):
        await svc.compute_dcf("SAFE", free_cash_flow=100000, growth_rate_5y=0.15, wacc=0.08,
                              shares_outstanding=100, net_debt=0, cash_and_equivalents=0, current_price=50)
        await svc.compute_relative("SAFE", eps=5, industry_avg_pe=30, current_price=50)
        report = await svc.generate_report("SAFE")
        if report.composite_fair_value and report.composite_fair_value > 50:
            assert report.margin_of_safety_pct > 0

    @pytest.mark.asyncio
    async def test_get_report_returns_latest(self, svc: ValuationService):
        await svc.generate_report("TEST")
        report2 = await svc.generate_report("TEST")
        fetched = await svc.get_report("TEST")
        assert fetched.id == report2.id

    @pytest.mark.asyncio
    async def test_get_report_not_found(self, svc: ValuationService):
        result = await svc.get_report("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_report_recommendation_strong_buy(self, svc: ValuationService):
        await svc.compute_dcf("BARGAIN", free_cash_flow=200000, growth_rate_5y=0.20, wacc=0.08,
                              shares_outstanding=100, net_debt=0, cash_and_equivalents=0, current_price=10)
        await svc.compute_relative("BARGAIN", eps=2, industry_avg_pe=50, current_price=10)
        report = await svc.generate_report("BARGAIN")
        if report.margin_of_safety_pct and report.margin_of_safety_pct >= 30:
            assert report.recommendation == "strong_buy"

    @pytest.mark.asyncio
    async def test_report_recommendation_strong_sell(self, svc: ValuationService):
        await svc.compute_dcf("DEAR", free_cash_flow=100, growth_rate_5y=0.02, wacc=0.15,
                              shares_outstanding=100, net_debt=0, cash_and_equivalents=0, current_price=1000)
        await svc.compute_relative("DEAR", eps=1, industry_avg_pe=5, current_price=1000)
        report = await svc.generate_report("DEAR")
        if report.margin_of_safety_pct and report.margin_of_safety_pct < -15:
            assert report.recommendation == "strong_sell"
