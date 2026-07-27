from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.opportunity_rejection import OpportunityRejection
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.services.opportunity_rejection_service import OpportunityRejectionService

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
    return OpportunityRejectionService(session)


@pytest_asyncio.fixture
async def seed_good_data(session):
    today = date.today()
    liq = MarketMicrostructure(
        symbol="GOOD", as_of_date=today, liquidity_score=85.0, liquidity_rating="high",
        volume=1_000_000, avg_volume_5d=900_000, avg_volume_20d=800_000,
        volume_ratio=1.25, avg_spread_pct=0.3,
    )
    session.add(liq)

    risk = RiskMetrics(
        symbol="GOOD", as_of_date=today, composite_risk_score=25.0, risk_rating="low",
        volatility_20d=0.2, volatility_60d=0.25,
    )
    session.add(risk)

    regime = MarketRegime(
        symbol="GOOD", as_of_date=today,
        trend_regime="bull", trend_score=75.0,
        volatility_regime="normal_volatility",
        momentum_20d=0.08, confidence=0.8,
    )
    session.add(regime)

    breadth = MarketBreadth(
        trade_date=today, advancing=1500, declining=800, unchanged=200,
        total_stocks=2500, advancing_volume=1_500_000_000,
        declining_volume=800_000_000, unchanged_volume=200_000_000,
        total_volume=2_500_000_000, new_highs=200, new_lows=50,
        advance_decline_ratio=1.88, breadth_oscillator=0.3,
        index_strength_score=70.0,
    )
    session.add(breadth)

    for i in range(5):
        article = NewsArticle(
            symbol="GOOD", title=f"Good news {i}", source="test",
            source_id=f"g{i}", url=f"http://test.com/g{i}",
            url_hash=f"g{i}h", published_at=datetime.now(timezone.utc) - timedelta(hours=i),
        )
        session.add(article)
        await session.flush()
        nlp = NewsNLPAnalysis(
            article_id=article.id, sentiment_label="POSITIVE",
            sentiment_positive=0.85, sentiment_negative=0.05,
            sentiment_neutral=0.10, sentiment_confidence=0.9,
        )
        session.add(nlp)

    fm1 = FundamentalMetric(
        symbol="GOOD", fiscal_year=2025, fiscal_period=1, period_type="FY",
        metric_name="profit_margin", value=15.0,
    )
    session.add(fm1)
    fm2 = FundamentalMetric(
        symbol="GOOD", fiscal_year=2025, fiscal_period=1, period_type="FY",
        metric_name="debt_to_equity", value=0.5,
    )
    session.add(fm2)
    fm3 = FundamentalMetric(
        symbol="GOOD", fiscal_year=2025, fiscal_period=1, period_type="FY",
        metric_name="revenue_growth_yoy", value=12.0,
    )
    session.add(fm3)

    await session.flush()


@pytest_asyncio.fixture
async def seed_bad_data(session):
    today = date.today()
    liq = MarketMicrostructure(
        symbol="BAD", as_of_date=today, liquidity_score=20.0, liquidity_rating="low",
        volume=10_000, avg_volume_5d=8_000, avg_volume_20d=5_000,
        volume_ratio=2.0, avg_spread_pct=5.0,
    )
    session.add(liq)

    risk = RiskMetrics(
        symbol="BAD", as_of_date=today, composite_risk_score=75.0, risk_rating="high",
        volatility_20d=0.6, volatility_60d=0.5,
    )
    session.add(risk)

    regime = MarketRegime(
        symbol="BAD", as_of_date=today,
        trend_regime="bear", trend_score=30.0,
        volatility_regime="high_volatility",
        momentum_20d=-0.12, confidence=0.3,
    )
    session.add(regime)

    breadth = MarketBreadth(
        trade_date=today, advancing=600, declining=1800, unchanged=100,
        total_stocks=2500, advancing_volume=600_000_000,
        declining_volume=1_800_000_000, unchanged_volume=100_000_000,
        total_volume=2_500_000_000, new_highs=30, new_lows=250,
        advance_decline_ratio=0.33, breadth_oscillator=-0.4,
        index_strength_score=25.0,
    )
    session.add(breadth)

    for i in range(3):
        article = NewsArticle(
            symbol="BAD", title=f"Bad news {i}", source="test",
            source_id=f"b{i}", url=f"http://test.com/b{i}",
            url_hash=f"b{i}h", published_at=datetime.now(timezone.utc) - timedelta(hours=i),
        )
        session.add(article)
        await session.flush()
        nlp = NewsNLPAnalysis(
            article_id=article.id, sentiment_label="NEGATIVE",
            sentiment_positive=0.15, sentiment_negative=0.75,
            sentiment_neutral=0.10, sentiment_confidence=0.8,
        )
        session.add(nlp)

    fm1 = FundamentalMetric(
        symbol="BAD", fiscal_year=2025, fiscal_period=1, period_type="FY",
        metric_name="profit_margin", value=-5.0,
    )
    session.add(fm1)
    fm2 = FundamentalMetric(
        symbol="BAD", fiscal_year=2025, fiscal_period=1, period_type="FY",
        metric_name="debt_to_equity", value=3.5,
    )
    session.add(fm2)
    fm3 = FundamentalMetric(
        symbol="BAD", fiscal_year=2025, fiscal_period=1, period_type="FY",
        metric_name="revenue_growth_yoy", value=-2.0,
    )
    session.add(fm3)

    await session.flush()


class TestEvaluate:
    async def test_evaluate_no_data(self, service):
        result = await service.evaluate("NODATA")
        assert result.symbol == "NODATA"
        assert result.is_rejected is True
        assert result.rejection_reason is not None

    async def test_evaluate_good_opportunity(self, service, seed_good_data):
        result = await service.evaluate("GOOD")
        assert result.is_rejected is False
        assert result.composite_score is not None
        assert result.composite_score > 50

    async def test_evaluate_bad_opportunity(self, service, seed_bad_data):
        result = await service.evaluate("BAD")
        assert result.is_rejected is True
        assert result.rejection_reason is not None

    async def test_evaluate_all_scores_present(self, service, seed_good_data):
        result = await service.evaluate("GOOD")
        for score in [result.liquidity_score, result.risk_score, result.news_score,
                       result.financial_score, result.trend_score, result.market_score]:
            assert score is not None

    async def test_evaluate_bad_liquidity_scores_low(self, service, seed_bad_data):
        result = await service.evaluate("BAD")
        assert result.liquidity_score is not None
        assert result.liquidity_score < 40

    async def test_evaluate_bad_risk_scores_high(self, service, seed_bad_data):
        result = await service.evaluate("BAD")
        assert result.risk_score is not None
        assert result.risk_score < 50

    async def test_evaluate_rejection_reasons(self, service, seed_bad_data):
        result = await service.evaluate("BAD")
        assert result.rejection_reason is not None
        assert len(result.rejection_reason) > 0

    async def test_evaluate_good_no_rejection_reasons(self, service, seed_good_data):
        result = await service.evaluate("GOOD")
        assert result.rejection_reason is None

    async def test_evaluate_direction(self, service, seed_good_data):
        result = await service.evaluate("GOOD", direction="bearish")
        assert result.direction == "bearish"


class TestQuery:
    async def test_get_evaluation(self, service, seed_good_data):
        ev = await service.evaluate("GOOD")
        found = await service.get_evaluation(ev.id)
        assert found is not None
        assert found.id == ev.id

    async def test_get_evaluation_not_found(self, service):
        found = await service.get_evaluation(9999)
        assert found is None

    async def test_get_evaluations(self, service, seed_good_data):
        await service.evaluate("GOOD")
        await service.evaluate("GOOD", direction="bearish")
        evals = await service.get_evaluations("GOOD")
        assert len(evals) > 0
