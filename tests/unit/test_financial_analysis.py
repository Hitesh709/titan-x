import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.financial_analysis import AnnualResult, FinancialAnalysis, Guidance, QuarterlyResult
from titan_x.services.financial_analysis_service import FinancialAnalysisService


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
def svc(session: AsyncSession) -> FinancialAnalysisService:
    return FinancialAnalysisService(session)


# ============================================================
# QUARTERLY RESULTS
# ============================================================

class TestQuarterlyResults:
    @pytest.mark.asyncio
    async def test_record_quarterly(self, svc: FinancialAnalysisService):
        qr = await svc.record_quarterly("RELIANCE", 2025, 1, revenue=100000, net_income=15000, eps_diluted=5.0)
        assert qr.symbol == "RELIANCE"
        assert qr.fiscal_year == 2025
        assert qr.quarter == 1
        assert qr.revenue == 100000
        assert qr.net_margin == 0.15
        assert qr.revenue_qoq_growth is None
        assert qr.revenue_yoy_growth is None

    @pytest.mark.asyncio
    async def test_record_quarterly_computes_margins(self, svc: FinancialAnalysisService):
        qr = await svc.record_quarterly("TCS", 2025, 1, revenue=50000, cost_of_revenue=30000, operating_income=10000, net_income=8000)
        assert qr.gross_profit == 20000
        assert qr.gross_margin == 0.4
        assert qr.operating_margin == 0.2
        assert qr.net_margin == 0.16

    @pytest.mark.asyncio
    async def test_record_quarterly_qoq_growth(self, svc: FinancialAnalysisService):
        await svc.record_quarterly("TEST", 2025, 1, revenue=100, eps_diluted=2.0)
        qr2 = await svc.record_quarterly("TEST", 2025, 2, revenue=150, eps_diluted=3.0)
        assert qr2.revenue_qoq_growth == 0.5
        assert qr2.eps_qoq_growth == 0.5

    @pytest.mark.asyncio
    async def test_record_quarterly_qoq_growth_wrap_year(self, svc: FinancialAnalysisService):
        await svc.record_quarterly("TEST", 2024, 4, revenue=100)
        qr2 = await svc.record_quarterly("TEST", 2025, 1, revenue=120)
        assert qr2.revenue_qoq_growth == 0.2

    @pytest.mark.asyncio
    async def test_record_quarterly_yoy_growth(self, svc: FinancialAnalysisService):
        await svc.record_quarterly("TEST", 2024, 1, revenue=100, eps_diluted=2.0)
        qr2 = await svc.record_quarterly("TEST", 2025, 1, revenue=130, eps_diluted=2.6)
        assert qr2.revenue_yoy_growth == 0.3
        assert qr2.eps_yoy_growth == 0.3

    @pytest.mark.asyncio
    async def test_get_quarterly(self, svc: FinancialAnalysisService):
        await svc.record_quarterly("TEST", 2025, 1, revenue=100)
        await svc.record_quarterly("TEST", 2025, 2, revenue=110)
        results = await svc.get_quarterly("TEST")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_quarterly_empty(self, svc: FinancialAnalysisService):
        results = await svc.get_quarterly("NONEXISTENT")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_quarterly(self, svc: FinancialAnalysisService):
        qr = await svc.record_quarterly("TEST", 2025, 1, revenue=100)
        ok = await svc.delete_quarterly(qr.id)
        assert ok is True
        assert await svc.delete_quarterly(qr.id) is False

    @pytest.mark.asyncio
    async def test_delete_quarterly_not_found(self, svc: FinancialAnalysisService):
        assert await svc.delete_quarterly(9999) is False

    @pytest.mark.asyncio
    async def test_record_quarterly_gross_profit_override(self, svc: FinancialAnalysisService):
        qr = await svc.record_quarterly("TEST", 2025, 1, revenue=100, cost_of_revenue=60, gross_profit=50)
        assert qr.gross_profit == 50
        assert qr.gross_margin == 0.5


# ============================================================
# ANNUAL RESULTS
# ============================================================

class TestAnnualResults:
    @pytest.mark.asyncio
    async def test_record_annual(self, svc: FinancialAnalysisService):
        ar = await svc.record_annual("RELIANCE", 2025, revenue=400000, net_income=60000, eps_diluted=20.0)
        assert ar.symbol == "RELIANCE"
        assert ar.fiscal_year == 2025
        assert ar.net_margin == 0.15

    @pytest.mark.asyncio
    async def test_record_annual_yoy_growth(self, svc: FinancialAnalysisService):
        await svc.record_annual("TEST", 2024, revenue=300, eps_diluted=10.0)
        ar2 = await svc.record_annual("TEST", 2025, revenue=360, eps_diluted=12.0)
        assert ar2.revenue_yoy_growth == 0.2
        assert ar2.eps_yoy_growth == 0.2

    @pytest.mark.asyncio
    async def test_record_annual_no_prior(self, svc: FinancialAnalysisService):
        ar = await svc.record_annual("TEST", 2025, revenue=100)
        assert ar.revenue_yoy_growth is None

    @pytest.mark.asyncio
    async def test_get_annual(self, svc: FinancialAnalysisService):
        await svc.record_annual("TEST", 2024, revenue=300)
        await svc.record_annual("TEST", 2025, revenue=360)
        results = await svc.get_annual("TEST")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_annual_empty(self, svc: FinancialAnalysisService):
        results = await svc.get_annual("NONEXISTENT")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_annual(self, svc: FinancialAnalysisService):
        ar = await svc.record_annual("TEST", 2025, revenue=100)
        ok = await svc.delete_annual(ar.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_delete_annual_not_found(self, svc: FinancialAnalysisService):
        assert await svc.delete_annual(9999) is False


# ============================================================
# GUIDANCE
# ============================================================

class TestGuidance:
    @pytest.mark.asyncio
    async def test_record_guidance(self, svc: FinancialAnalysisService):
        g = await svc.record_guidance("RELIANCE", 2026, "annual", revenue_low=450000, revenue_high=480000, eps_low=22.0, eps_high=24.0)
        assert g.symbol == "RELIANCE"
        assert g.revenue_low == 450000
        assert g.status == "active"

    @pytest.mark.asyncio
    async def test_get_guidance(self, svc: FinancialAnalysisService):
        await svc.record_guidance("TEST", 2026, "annual", revenue_low=100, revenue_high=120)
        await svc.record_guidance("TEST", 2027, "annual", revenue_low=130, revenue_high=150)
        results = await svc.get_guidance("TEST")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_guidance_empty(self, svc: FinancialAnalysisService):
        results = await svc.get_guidance("NONEXISTENT")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_guidance(self, svc: FinancialAnalysisService):
        g = await svc.record_guidance("TEST", 2026, "annual")
        ok = await svc.delete_guidance(g.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_delete_guidance_not_found(self, svc: FinancialAnalysisService):
        assert await svc.delete_guidance(9999) is False


# ============================================================
# AI ANALYSIS
# ============================================================

class TestAnalysis:
    @pytest.mark.asyncio
    async def test_analyze_with_minimal_data(self, svc: FinancialAnalysisService):
        ar = await svc.analyze("NEWCO")
        assert ar.symbol == "NEWCO"
        assert ar.overall_score is not None
        assert ar.signal is not None
        assert ar.summary_text is not None
        assert "NEWCO" in ar.summary_text

    @pytest.mark.asyncio
    async def test_analyze_strong_growth(self, svc: FinancialAnalysisService):
        await svc.record_annual("GROWTH", 2023, revenue=100, net_income=20, eps_diluted=2.0)
        await svc.record_annual("GROWTH", 2024, revenue=150, net_income=30, eps_diluted=3.0)
        await svc.record_quarterly("GROWTH", 2025, 1, revenue=50, net_income=12, eps_diluted=1.2)
        await svc.record_guidance("GROWTH", 2025, "annual", revenue_low=180, revenue_high=200)

        ar = await svc.analyze("GROWTH")
        assert ar.overall_score >= 50
        assert ar.signal in ("strong_buy", "buy")

    @pytest.mark.asyncio
    async def test_analyze_persists(self, svc: FinancialAnalysisService):
        ar = await svc.analyze("PERSIST")
        fetched = await svc.get_analysis("PERSIST")
        assert fetched is not None
        assert fetched.id == ar.id
        assert fetched.signal == ar.signal

    @pytest.mark.asyncio
    async def test_get_analysis_not_found(self, svc: FinancialAnalysisService):
        assert await svc.get_analysis("NONEXISTENT") is None

    @pytest.mark.asyncio
    async def test_analyze_overwrites_previous(self, svc: FinancialAnalysisService):
        a1 = await svc.analyze("OVERWRITE")
        a2 = await svc.analyze("OVERWRITE")
        assert a2.id != a1.id
        assert a2.analysis_date > a1.analysis_date

    @pytest.mark.asyncio
    async def test_analyze_with_guidance_beat(self, svc: FinancialAnalysisService):
        await svc.record_quarterly("BEAT", 2025, 1, revenue=120)
        await svc.record_guidance("BEAT", 2025, "annual", revenue_low=100, revenue_high=110)
        ar = await svc.analyze("BEAT")
        assert ar.guidance_score > 50

    @pytest.mark.asyncio
    async def test_analyze_negative_growth(self, svc: FinancialAnalysisService):
        await svc.record_annual("DECLINE", 2023, revenue=200, net_income=40, eps_diluted=4.0)
        await svc.record_annual("DECLINE", 2024, revenue=150, net_income=20, eps_diluted=2.0)
        await svc.record_quarterly("DECLINE", 2025, 1, revenue=30, net_income=2, eps_diluted=0.2)
        ar = await svc.analyze("DECLINE")
        assert ar.overall_score < 60
        assert ar.signal in ("sell", "strong_sell", "hold")
