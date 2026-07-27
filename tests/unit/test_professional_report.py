import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.chart_pattern import SupportResistance
from titan_x.models.company import Company
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.models.professional_report import ProfessionalReport
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.technical import TechnicalIndicator
from titan_x.services.professional_report_service import ProfessionalReportService

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
    return ProfessionalReportService(session)


@pytest_asyncio.fixture
async def seed_company(session):
    c = Company(
        symbol="TEST",
        company_name="Test Corp",
        isin="US1234567890",
        sector="Technology",
        industry="Software",
        exchange="NYSE",
        status="active",
    )
    session.add(c)
    await session.flush()


@pytest_asyncio.fixture
async def seed_prices(session):
    today = date.today()
    for i in range(100):
        dp = DailyPrice(
            symbol="TEST",
            trade_date=today - timedelta(days=(99 - i)),
            open=100.0 + i * 0.5,
            high=101.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=100.0 + i * 0.5,
            volume=1_000_000,
        )
        session.add(dp)
    await session.flush()


@pytest_asyncio.fixture
async def seed_regime(session):
    regime = MarketRegime(
        symbol="TEST",
        as_of_date=date.today(),
        trend_regime="bull",
        volatility_regime="normal_volatility",
        trend_score=70.0,
        volatility_score=50.0,
        confidence=0.8,
    )
    session.add(regime)
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
async def seed_risk(session):
    rm = RiskMetrics(
        symbol="TEST",
        as_of_date=date.today(),
        composite_risk_score=35.0,
        volatility_20d=0.25,
        volatility_60d=0.22,
        max_drawdown_1m=-5.2,
        max_drawdown_3m=-8.1,
        max_drawdown_6m=-12.5,
        event_risk_score=20.0,
    )
    session.add(rm)
    await session.flush()


@pytest_asyncio.fixture
async def seed_technical(session):
    today = date.today()
    indicators = [
        ("rsi", "14", 62.5, None, None),
        ("sma", "20", 145.0, None, None),
        ("sma", "50", 138.0, None, None),
        ("macd", "12_26_9", 2.5, 1.8, 0.7),
        ("bb", "20_2", 155.0, 165.0, 145.0),
        ("volume", "20", 1_200_000, 1_100_000, None),
        ("obv", "20", 500_000, None, None),
        ("atr", "14", 3.2, None, None),
    ]
    for ind, params_hash, val, v2, v3 in indicators:
        ti = TechnicalIndicator(
            symbol="TEST",
            trade_date=today,
            indicator=ind,
            params_hash=params_hash,
            value=val,
            value_secondary=v2,
            value_tertiary=v3,
        )
        session.add(ti)
    await session.flush()


@pytest_asyncio.fixture
async def seed_sr(session):
    sr = SupportResistance(
        symbol="TEST",
        level_type="support",
        price_level=130.0,
        strength_score=75.0,
        touch_count=5,
        first_detected=date.today() - timedelta(days=30),
        last_tested=date.today() - timedelta(days=2),
        is_active=True,
    )
    session.add(sr)
    sr2 = SupportResistance(
        symbol="TEST",
        level_type="resistance",
        price_level=160.0,
        strength_score=70.0,
        touch_count=4,
        first_detected=date.today() - timedelta(days=25),
        last_tested=date.today() - timedelta(days=1),
        is_active=True,
    )
    session.add(sr2)
    await session.flush()


@pytest_asyncio.fixture
async def seed_fundamental(session):
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
        fm = FundamentalMetric(
            symbol="TEST",
            fiscal_year=2025,
            fiscal_period=4,
            period_type="annual",
            metric_name=name,
            value=val,
        )
        session.add(fm)
    await session.flush()


@pytest_asyncio.fixture
async def seed_news(session):
    today = date.today()
    for i in range(3):
        na = NewsArticle(
            title=f"Test Article {i}",
            source="TestSource",
            source_id=f"src-{i}",
            url=f"https://test.com/{i}",
            url_hash=f"hash{i}",
            symbol="TEST",
            published_at=today - timedelta(days=i),
        )
        session.add(na)
        await session.flush()
        nlp = NewsNLPAnalysis(
            article_id=na.id,
            sentiment_positive=0.6 + i * 0.1,
            sentiment_negative=0.2 - i * 0.05,
            sentiment_neutral=0.2 - i * 0.05,
        )
        session.add(nlp)
    await session.flush()


class TestGenerate:
    async def test_generate_basic(self, service, seed_prices):
        report = await service.generate("TEST")
        assert report.symbol == "TEST"
        assert report.current_price > 0
        assert report.html_content is not None
        assert "Professional Report" in report.html_content
        assert "<!DOCTYPE html>" in report.html_content

    async def test_generate_with_company(self, service, seed_company, seed_prices):
        report = await service.generate("TEST")
        summary = json.loads(report.summary_json)
        assert summary["company_name"] == "Test Corp"
        assert summary["sector"] == "Technology"

    async def test_generate_with_all_data(
        self, service, seed_prices, seed_company, seed_regime,
        seed_liquidity, seed_technical, seed_sr, seed_fundamental,
        seed_risk, seed_news,
    ):
        report = await service.generate("TEST")
        assert report.symbol == "TEST"
        assert report.current_price > 0

        summary = json.loads(report.summary_json)
        assert summary["trend_regime"] == "bull"
        assert summary["liquidity_rating"] == "high"

        tech = json.loads(report.technical_json)
        assert tech["rsi_14"] is not None
        assert len(tech["support_levels"]) > 0
        assert len(tech["resistance_levels"]) > 0

        fund = json.loads(report.fundamental_json)
        assert fund["available"] is True
        assert fund.get("pe_ratio") == 15.5

        news = json.loads(report.news_json)
        assert news["total_articles"] > 0
        assert news["avg_sentiment_positive"] is not None

        risk = json.loads(report.risk_json)
        assert risk["composite_risk_score"] is not None

        pred = json.loads(report.prediction_json)
        assert pred["available"] is True
        assert pred["target_1_price"] is not None

    async def test_generate_bearish(self, service, seed_prices):
        report = await service.generate("TEST", direction="bearish")
        assert report.direction == "bearish"
        pred = json.loads(report.prediction_json)
        assert pred["target_1_pct"] < 0

    async def test_generate_no_data(self, service):
        report = await service.generate("NODATA")
        assert report.symbol == "NODATA"
        assert report.current_price == 0.0
        summary = json.loads(report.summary_json)
        assert summary["company_name"] is None

    async def test_html_contains_sections(self, service, seed_prices):
        report = await service.generate("TEST")
        html = report.html_content
        assert "Technical Analysis" in html
        assert "Fundamental Analysis" in html
        assert "News & Sentiment" in html
        assert "Risk Assessment" in html
        assert "Price Prediction" in html

    async def test_html_contains_svg(self, service, seed_prices, seed_fundamental):
        report = await service.generate("TEST")
        html = report.html_content
        assert "<svg" in html
        assert "</svg>" in html


class TestQuery:
    async def test_get_report(self, service, seed_prices):
        report = await service.generate("TEST")
        found = await service.get_report(report.id)
        assert found is not None
        assert found.id == report.id

    async def test_get_report_not_found(self, service):
        found = await service.get_report(9999)
        assert found is None

    async def test_get_reports(self, service, seed_prices):
        await service.generate("TEST")
        await service.generate("TEST", direction="bearish")
        reports = await service.get_reports("TEST")
        assert len(reports) == 2

    async def test_get_reports_empty(self, service):
        reports = await service.get_reports("EMPTY")
        assert len(reports) == 0

    async def test_get_reports_ordering(self, service, seed_prices):
        r1 = await service.generate("TEST")
        r2 = await service.generate("TEST")
        reports = await service.get_reports("TEST")
        assert reports[0].id >= reports[1].id
