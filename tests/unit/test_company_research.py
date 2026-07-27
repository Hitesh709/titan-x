import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.company_research import CompanyResearch
from titan_x.models.corporate_tracking import ShareholdingPattern
from titan_x.models.financial import FinancialLineItem, FinancialStatement
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.knowledge_graph import CompanyPromoter, EntityEvent, Promoter, Subsidiary
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.services.company_research_service import CompanyResearchService

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
    return CompanyResearchService(session)


@pytest_asyncio.fixture
async def seed_company(session):
    c = Company(
        symbol="TEST",
        company_name="Test Corp",
        isin="US1234567890",
        sector="Technology",
        industry="Software",
        exchange="NYSE",
        market_cap=50_000_000_000,
        listing_date=date(2010, 1, 1),
        status="active",
        description="A leading technology company specializing in software solutions and cloud computing.",
        website="https://testcorp.com",
    )
    session.add(c)
    await session.flush()

    c2 = Company(
        symbol="PEER1",
        company_name="Peer One Inc",
        isin="US9876543210",
        sector="Technology",
        industry="Software",
        exchange="NYSE",
        market_cap=30_000_000_000,
        status="active",
    )
    session.add(c2)
    await session.flush()

    c3 = Company(
        symbol="PEER2",
        company_name="Peer Two Ltd",
        isin="US5555555555",
        sector="Technology",
        industry="Software",
        exchange="NASDAQ",
        market_cap=10_000_000_000,
        status="active",
    )
    session.add(c3)
    await session.flush()

    # Promoter
    p = Promoter(name="Founder Family", promoter_type="individual")
    session.add(p)
    await session.flush()
    cp = CompanyPromoter(company_id=c.id, promoter_id=p.id, ownership_pct=35.0, role="Promoter")
    session.add(cp)

    # Subsidiary
    sub = Subsidiary(parent_company_id=c.id, subsidiary_company_id=c2.id, ownership_pct=100.0, relationship_type="subsidiary")
    session.add(sub)

    # Event
    ev = EntityEvent(
        company_id=c.id,
        event_type="product_launch",
        event_date=date.today() - timedelta(days=10),
        title="New AI Platform Launch",
        description="Launched next-gen AI platform",
        impact_score=85.0,
    )
    session.add(ev)

    await session.flush()


@pytest_asyncio.fixture
async def seed_prices(session):
    today = date.today()
    for i in range(252):
        dp = DailyPrice(
            symbol="TEST",
            trade_date=today - timedelta(days=(251 - i)),
            open=100.0 + i * 0.2,
            high=101.0 + i * 0.2,
            low=99.0 + i * 0.2,
            close=100.0 + i * 0.2,
            volume=1_000_000,
        )
        session.add(dp)
    await session.flush()


@pytest_asyncio.fixture
async def seed_financials(session):
    stmt = FinancialStatement(
        symbol="TEST",
        fiscal_year=2025,
        fiscal_period=4,
        period_type="annual",
        statement_type="income_statement",
        filing_date=date.today() - timedelta(days=30),
    )
    session.add(stmt)
    await session.flush()
    items = [
        ("revenue", "Total Revenue", 10_000_000_000, "USD"),
        ("cost_of_revenue", "Cost of Revenue", 5_500_000_000, "USD"),
        ("gross_profit", "Gross Profit", 4_500_000_000, "USD"),
        ("operating_income", "Operating Income", 1_800_000_000, "USD"),
        ("net_income", "Net Income", 1_200_000_000, "USD"),
    ]
    for concept, label, val, unit in items:
        session.add(FinancialLineItem(
            statement_id=stmt.id, concept=concept, label=label, value=val, unit=unit,
        ))
    await session.flush()

    metrics = [
        ("pe_ratio", 15.5),
        ("pb_ratio", 2.1),
        ("debt_to_equity", 0.45),
        ("current_ratio", 2.3),
        ("profit_margin", 0.12),
        ("revenue_growth", 0.08),
        ("eps_growth", 0.15),
        ("roe", 0.18),
        ("roa", 0.09),
        ("dividend_yield", 0.025),
        ("market_cap", 50_000_000_000),
    ]
    for name, val in metrics:
        session.add(FundamentalMetric(
            symbol="TEST",
            fiscal_year=2025,
            fiscal_period=4,
            period_type="annual",
            metric_name=name,
            value=val,
        ))
        session.add(FundamentalMetric(
            symbol="PEER1",
            fiscal_year=2025,
            fiscal_period=4,
            period_type="annual",
            metric_name=name,
            value=val * (0.8 if name != "debt_to_equity" else 1.2),
        ))
    await session.flush()


@pytest_asyncio.fixture
async def seed_risk(session):
    rm = RiskMetrics(
        symbol="TEST",
        as_of_date=date.today(),
        composite_risk_score=35.0,
        risk_rating="moderate",
        volatility_20d=0.25,
        volatility_60d=0.22,
        max_drawdown_1m=-5.2,
        max_drawdown_3m=-8.1,
        max_drawdown_6m=-12.5,
        event_risk_score=20.0,
        news_count_30d=15,
        gap_frequency_20d=0.05,
    )
    session.add(rm)
    await session.flush()


@pytest_asyncio.fixture
async def seed_liquidity(session):
    liq = MarketMicrostructure(
        symbol="TEST",
        as_of_date=date.today(),
        volume=1_500_000,
        avg_volume_5d=1_200_000,
        avg_volume_20d=1_000_000,
        volume_ratio=1.5,
        liquidity_score=75.0,
        liquidity_rating="high",
        avg_spread_pct=0.5,
    )
    session.add(liq)
    await session.flush()


@pytest_asyncio.fixture
async def seed_regime(session):
    reg = MarketRegime(
        symbol="TEST",
        as_of_date=date.today(),
        trend_regime="bull",
        volatility_regime="normal_volatility",
        trend_score=70.0,
        volatility_score=50.0,
        confidence=0.8,
    )
    session.add(reg)
    await session.flush()


@pytest_asyncio.fixture
async def seed_sector(session):
    sp = SectorPerformance(
        sector="Technology",
        as_of_date=date.today(),
        period_label="1M",
        return_pct=3.5,
        momentum_score=65.0,
        relative_strength=1.2,
        rank=3,
    )
    session.add(sp)
    await session.flush()


class TestGenerate:
    async def test_generate_basic(self, service, seed_company):
        research = await service.generate("TEST")
        assert research.symbol == "TEST"
        assert research.html_content is not None
        assert "Company Research" in research.html_content
        assert "<!DOCTYPE html>" in research.html_content

    async def test_generate_business_section(self, service, seed_company):
        research = await service.generate("TEST")
        biz = json.loads(research.business_json)
        assert biz.get("available") is True
        assert biz.get("company_name") == "Test Corp"
        assert biz.get("sector") == "Technology"
        assert biz.get("subsidiaries")
        assert biz.get("promoters")
        assert biz.get("recent_events")

    async def test_generate_financials(self, service, seed_company, seed_financials):
        research = await service.generate("TEST")
        fin = json.loads(research.financials_json)
        assert fin.get("available") is True
        assert fin.get("key_metrics", {}).get("pe_ratio") == 15.5
        assert len(fin.get("statements", [])) > 0

    async def test_generate_risks(self, service, seed_company, seed_risk, seed_liquidity, seed_regime):
        research = await service.generate("TEST")
        risk = json.loads(research.risks_json)
        assert risk.get("available") is True
        assert risk.get("composite_risk_score") == 35.0
        assert risk.get("liquidity_rating") == "high"
        assert risk.get("trend_regime") == "bull"

    async def test_generate_growth(self, service, seed_company, seed_prices, seed_financials, seed_sector):
        research = await service.generate("TEST")
        gr = json.loads(research.growth_json)
        assert gr.get("available") is True
        assert gr.get("current_price") is not None
        assert gr.get("price_returns", {}).get("1y") is not None
        assert gr.get("sector_comparison") is not None

    async def test_generate_competition(self, service, seed_company, seed_financials):
        research = await service.generate("TEST")
        comp = json.loads(research.competition_json)
        assert comp.get("available") is True
        assert comp.get("peer_count", 0) >= 2
        assert len(comp.get("peers", [])) >= 2

    async def test_generate_ai_summary(self, service, seed_company, seed_financials, seed_prices, seed_risk, seed_liquidity, seed_regime, seed_sector):
        research = await service.generate("TEST")
        summary = research.ai_summary
        assert summary is not None
        assert len(summary) > 50
        assert "Test Corp" in summary
        assert "Technology" in summary

    async def test_generate_all_sections(self, service, seed_company, seed_prices, seed_financials,
                                          seed_risk, seed_liquidity, seed_regime, seed_sector):
        research = await service.generate("TEST")
        assert research.business_json is not None
        assert research.financials_json is not None
        assert research.risks_json is not None
        assert research.growth_json is not None
        assert research.competition_json is not None
        assert research.ai_summary is not None
        assert research.html_content is not None

    async def test_generate_no_data(self, service):
        research = await service.generate("NODATA")
        biz = json.loads(research.business_json)
        assert biz.get("available") is False

    async def test_html_contains_sections(self, service, seed_company, seed_financials):
        research = await service.generate("TEST")
        html = research.html_content
        assert "Business Overview" in html
        assert "Financials" in html
        assert "Risk Assessment" in html
        assert "Growth Analysis" in html
        assert "Competition" in html
        assert "AI Summary" in html

    async def test_html_contains_svg(self, service, seed_company, seed_financials):
        research = await service.generate("TEST")
        html = research.html_content
        assert "<!DOCTYPE html>" in html


class TestQuery:
    async def test_get_research(self, service, seed_company):
        r = await service.generate("TEST")
        found = await service.get_research(r.id)
        assert found is not None
        assert found.id == r.id

    async def test_get_research_not_found(self, service):
        found = await service.get_research(9999)
        assert found is None

    async def test_get_research_by_symbol(self, service, seed_company):
        r = await service.generate("TEST")
        found = await service.get_research_by_symbol("TEST")
        assert found is not None
        assert found.id == r.id

    async def test_get_research_by_symbol_not_found(self, service):
        found = await service.get_research_by_symbol("NONE")
        assert found is None

    async def test_list_research(self, service, seed_company):
        await service.generate("TEST")
        await service.generate("TEST")
        records = await service.list_research("TEST")
        assert len(records) == 2
