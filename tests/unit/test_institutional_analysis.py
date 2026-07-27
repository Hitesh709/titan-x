import json
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.institutional_holdings import (
    DIIHolding,
    ETFHolding,
    FIIHolding,
    InstitutionalAnalysis,
    MutualFundHolding,
)
from titan_x.services.institutional_analysis_service import InstitutionalAnalysisService


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
async def company(session: AsyncSession) -> Company:
    c = Company(symbol="INST", company_name="Institutional Test Corp", isin="IN00099", exchange="NSE")
    session.add(c)
    await session.flush()
    return c


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> InstitutionalAnalysisService:
    return InstitutionalAnalysisService(session)


# ============================================================
# FII CRUD
# ============================================================

class TestFIIHoldingCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.create_fii_holding(company_id=company.id, fii_name="Goldman Sachs",
                                          percentage=2.5, quarter=1, year=2025, filing_date=date(2025, 3, 31))
        assert r.fii_name == "Goldman Sachs"
        assert r.percentage == 2.5

    @pytest.mark.asyncio
    async def test_list(self, svc: InstitutionalAnalysisService, company: Company):
        for i in range(3):
            await svc.create_fii_holding(company_id=company.id, fii_name=f"FII{i}",
                                          percentage=1.0 + i, quarter=1, year=2025, filing_date=date(2025, 3, 31))
        rows, total = await svc.list_fii_holdings()
        assert total == 3

    @pytest.mark.asyncio
    async def test_filter_by_company(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_fii_holding(company_id=company.id, fii_name="FII-A",
                                      percentage=3.0, quarter=1, year=2025, filing_date=date(2025, 3, 31))
        rows, total = await svc.list_fii_holdings(company_id=company.id)
        assert total == 1

    @pytest.mark.asyncio
    async def test_delete(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.create_fii_holding(company_id=company.id, fii_name="Del",
                                          percentage=1.0, quarter=1, year=2025, filing_date=date(2025, 3, 31))
        assert await svc.delete_fii_holding(r.id) is True
        assert await svc.get_fii_holding(r.id) is None


# ============================================================
# DII CRUD
# ============================================================

class TestDIIHoldingCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                          category="Insurance", percentage=5.0,
                                          quarter=1, year=2025, filing_date=date(2025, 3, 31))
        assert r.dii_name == "LIC"
        assert r.category == "Insurance"

    @pytest.mark.asyncio
    async def test_list(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                      percentage=5.0, quarter=1, year=2025, filing_date=date(2025, 3, 31))
        rows, total = await svc.list_dii_holdings()
        assert total == 1


# ============================================================
# MF CRUD
# ============================================================

class TestMFHoldingCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.create_mf_holding(company_id=company.id, amc="HDFC AMC",
                                         scheme_name="HDFC Top 100 Fund",
                                         percentage=3.2, quarter=1, year=2025,
                                         filing_date=date(2025, 3, 31))
        assert r.amc == "HDFC AMC"
        assert r.scheme_name == "HDFC Top 100 Fund"

    @pytest.mark.asyncio
    async def test_filter_by_amc(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_mf_holding(company_id=company.id, amc="ICICI AMC",
                                     scheme_name="ICICI Fund", percentage=2.0,
                                     quarter=1, year=2025, filing_date=date(2025, 3, 31))
        rows, total = await svc.list_mf_holdings(amc="ICICI AMC")
        assert total == 1


# ============================================================
# ETF CRUD
# ============================================================

class TestETFHoldingCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.create_etf_holding(company_id=company.id, etf_name="Nippon India ETF Nifty 50",
                                          issuer="Nippon India", percentage=1.5,
                                          quarter=1, year=2025, filing_date=date(2025, 3, 31))
        assert r.etf_name == "Nippon India ETF Nifty 50"
        assert r.percentage == 1.5

    @pytest.mark.asyncio
    async def test_list(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_etf_holding(company_id=company.id, etf_name="ETF1",
                                      issuer="Issuer1", percentage=1.0,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        rows, total = await svc.list_etf_holdings()
        assert total == 1


# ============================================================
# AI SCORING: FII
# ============================================================

class TestFIIScore:
    @pytest.mark.asyncio
    async def test_no_data(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.analyze_fii(company.id)
        assert r["fii_score"] == 50.0
        assert r["total_fiis"] == 0

    @pytest.mark.asyncio
    async def test_increasing_fii(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=3.0, quarter=4, year=2024,
                                      filing_date=date(2024, 12, 31))
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=5.0, change_percentage=2.0,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_fii(company.id)
        assert r["fii_score"] > 50
        assert r["pct_change"] > 0

    @pytest.mark.asyncio
    async def test_decreasing_fii(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=8.0, quarter=4, year=2024,
                                      filing_date=date(2024, 12, 31))
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=4.0, change_percentage=-4.0,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_fii(company.id)
        assert r["fii_score"] < 50
        assert r["pct_change"] < 0

    @pytest.mark.asyncio
    async def test_multiple_fiis(self, svc: InstitutionalAnalysisService, company: Company):
        for name in ["FII1", "FII2", "FII3", "FII4", "FII5",
                      "FII6", "FII7", "FII8", "FII9", "FII10"]:
            await svc.create_fii_holding(company_id=company.id, fii_name=name,
                                          percentage=1.0, quarter=1, year=2025,
                                          filing_date=date(2025, 3, 31))
        r = await svc.analyze_fii(company.id)
        assert r["total_fiis"] >= 10

    @pytest.mark.asyncio
    async def test_top_fiis(self, svc: InstitutionalAnalysisService, company: Company):
        for i, name in enumerate(["Large", "Medium", "Small"]):
            await svc.create_fii_holding(company_id=company.id, fii_name=name,
                                          percentage=10.0 - i * 3, quarter=1, year=2025,
                                          filing_date=date(2025, 3, 31))
        r = await svc.analyze_fii(company.id)
        assert len(r["top_fiis"]) == 3
        assert r["top_fiis"][0]["name"] == "Large"


# ============================================================
# AI SCORING: DII
# ============================================================

class TestDIIScore:
    @pytest.mark.asyncio
    async def test_increasing(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                      category="Insurance", percentage=4.0,
                                      quarter=4, year=2024, filing_date=date(2024, 12, 31))
        await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                      category="Insurance", percentage=6.0,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_dii(company.id)
        assert r["dii_score"] > 50

    @pytest.mark.asyncio
    async def test_multiple_categories(self, svc: InstitutionalAnalysisService, company: Company):
        for cat in ["Insurance", "Bank", "Pension Fund", "MF"]:
            await svc.create_dii_holding(company_id=company.id, dii_name=f"DII-{cat}",
                                          category=cat, percentage=1.0,
                                          quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_dii(company.id)
        assert len(r["categories"]) >= 3


# ============================================================
# AI SCORING: MF
# ============================================================

class TestMFScore:
    @pytest.mark.asyncio
    async def test_increasing(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_mf_holding(company_id=company.id, amc="HDFC",
                                     scheme_name="HDFC Fund", percentage=2.0,
                                     quarter=4, year=2024, filing_date=date(2024, 12, 31))
        await svc.create_mf_holding(company_id=company.id, amc="HDFC",
                                     scheme_name="HDFC Fund", percentage=4.0,
                                     quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_mf(company.id)
        assert r["mf_score"] > 50

    @pytest.mark.asyncio
    async def test_top_schemes(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_mf_holding(company_id=company.id, amc="AMC1",
                                     scheme_name="Top Scheme", percentage=5.0,
                                     quarter=1, year=2025, filing_date=date(2025, 3, 31))
        await svc.create_mf_holding(company_id=company.id, amc="AMC2",
                                     scheme_name="Other Scheme", percentage=2.0,
                                     quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_mf(company.id)
        assert r["top_schemes"][0]["scheme_name"] == "Top Scheme"
        assert len(r["top_amcs"]) == 2

    @pytest.mark.asyncio
    async def test_multiple_amcs(self, svc: InstitutionalAnalysisService, company: Company):
        for i in range(6):
            await svc.create_mf_holding(company_id=company.id, amc=f"AMC{i}",
                                         scheme_name=f"Fund{i}", percentage=1.0,
                                         quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_mf(company.id)
        assert r["unique_amcs"] >= 5

    @pytest.mark.asyncio
    async def test_new_schemes(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_mf_holding(company_id=company.id, amc="AMC1",
                                     scheme_name="Old Fund", percentage=2.0,
                                     quarter=4, year=2024, filing_date=date(2024, 12, 31))
        await svc.create_mf_holding(company_id=company.id, amc="AMC1",
                                     scheme_name="New Fund", percentage=3.0,
                                     quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_mf(company.id)
        assert r["scheme_change"] >= 0


# ============================================================
# AI SCORING: ETF
# ============================================================

class TestETFScore:
    @pytest.mark.asyncio
    async def test_increasing(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_etf_holding(company_id=company.id, etf_name="ETF1",
                                      issuer="Issuer1", percentage=1.0,
                                      quarter=4, year=2024, filing_date=date(2024, 12, 31))
        await svc.create_etf_holding(company_id=company.id, etf_name="ETF1",
                                      issuer="Issuer1", percentage=2.5,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_etf(company.id)
        assert r["etf_score"] > 50

    @pytest.mark.asyncio
    async def test_multiple_etfs(self, svc: InstitutionalAnalysisService, company: Company):
        for i in range(5):
            await svc.create_etf_holding(company_id=company.id, etf_name=f"ETF{i}",
                                          issuer="Issuer1", percentage=1.0,
                                          quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_etf(company.id)
        assert r["total_etfs"] == 5
        assert r["etf_score"] > 50


# ============================================================
# INSTITUTIONAL TRENDS
# ============================================================

class TestInstitutionalTrends:
    @pytest.mark.asyncio
    async def test_trends_empty(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.analyze_institutional_trends(company.id)
        assert r["trend_score"] == 50.0

    @pytest.mark.asyncio
    async def test_trends_with_data(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=5.0, quarter=1, year=2025,
                                      filing_date=date(2025, 3, 31))
        await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                      percentage=4.0, quarter=1, year=2025,
                                      filing_date=date(2025, 3, 31))
        await svc.create_mf_holding(company_id=company.id, amc="HDFC",
                                     scheme_name="Fund", percentage=3.0,
                                     quarter=1, year=2025, filing_date=date(2025, 3, 31))
        await svc.create_etf_holding(company_id=company.id, etf_name="ETF1",
                                      issuer="I1", percentage=1.0,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_institutional_trends(company.id)
        assert r["trend_score"] >= 0
        assert "fii_analysis" in r
        assert "dii_analysis" in r
        assert "mf_analysis" in r
        assert "etf_analysis" in r
        assert r["aggregate"]["fii_score"] is not None
        assert r["aggregate"]["dii_score"] is not None

    @pytest.mark.asyncio
    async def test_divergence_both_bullish(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=5.0, quarter=4, year=2024,
                                      filing_date=date(2024, 12, 31))
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=8.0, change_percentage=3.0,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                      percentage=3.0, quarter=4, year=2024,
                                      filing_date=date(2024, 12, 31))
        await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                      percentage=6.0, change_percentage=3.0,
                                      quarter=1, year=2025, filing_date=date(2025, 3, 31))
        r = await svc.analyze_institutional_trends(company.id)
        assert r["divergence_signal"] == "both_bullish"


# ============================================================
# FULL ANALYSIS
# ============================================================

class TestFullAnalysis:
    @pytest.mark.asyncio
    async def test_generate(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.generate_analysis(company.id)
        assert r.company_id == company.id
        assert r.signal in ("strong_buy", "buy", "hold", "sell", "strong_sell")
        assert r.confidence is not None

    @pytest.mark.asyncio
    async def test_generate_with_data(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.create_fii_holding(company_id=company.id, fii_name="FII1",
                                      percentage=5.0, quarter=1, year=2025,
                                      filing_date=date(2025, 3, 31))
        await svc.create_dii_holding(company_id=company.id, dii_name="LIC",
                                      percentage=4.0, quarter=1, year=2025,
                                      filing_date=date(2025, 3, 31))
        r = await svc.generate_analysis(company.id)
        insights = json.loads(r.insights_json)
        assert len(insights["insights"]) > 0
        assert r.fii_score is not None
        assert r.dii_score is not None

    @pytest.mark.asyncio
    async def test_latest(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.generate_analysis(company.id)
        r = await svc.get_latest_analysis(company.id)
        assert r is not None

    @pytest.mark.asyncio
    async def test_list(self, svc: InstitutionalAnalysisService, company: Company):
        await svc.generate_analysis(company.id)
        rows, total = await svc.list_analyses()
        assert total == 1

    @pytest.mark.asyncio
    async def test_delete(self, svc: InstitutionalAnalysisService, company: Company):
        r = await svc.generate_analysis(company.id)
        assert await svc.delete_analysis(r.id) is True
        assert await svc.get_analysis(r.id) is None
