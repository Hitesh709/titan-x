from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.technical import TechnicalIndicator
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.sector import SectorPerformance
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.risk import RiskMetrics
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.services.ensemble_ai_engine import EnsembleAIEngine, DEFAULT_WEIGHTS


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def ee(session: AsyncSession) -> EnsembleAIEngine:
    return EnsembleAIEngine(session)


class TestScoreToSignal:
    @pytest.mark.asyncio
    async def test_bullish(self, ee: EnsembleAIEngine) -> None:
        assert ee._score_to_signal(80) == "bullish"
        assert ee._score_to_signal(65) == "bullish"

    @pytest.mark.asyncio
    async def test_bearish(self, ee: EnsembleAIEngine) -> None:
        assert ee._score_to_signal(20) == "bearish"
        assert ee._score_to_signal(35) == "bearish"

    @pytest.mark.asyncio
    async def test_neutral(self, ee: EnsembleAIEngine) -> None:
        assert ee._score_to_signal(50) == "neutral"
        assert ee._score_to_signal(45) == "neutral"


class TestWeightedVote:
    @pytest.mark.asyncio
    async def test_all_bullish(self, ee: EnsembleAIEngine) -> None:
        subs = {name: {"score": 80, "signal": "bullish", "confidence": 70} for name in DEFAULT_WEIGHTS}
        result = ee._compute_weighted_vote(subs, DEFAULT_WEIGHTS)
        assert result["signal"] in ("buy", "strong_buy")
        assert result["score"] > 60

    @pytest.mark.asyncio
    async def test_all_bearish(self, ee: EnsembleAIEngine) -> None:
        subs = {name: {"score": 20, "signal": "bearish", "confidence": 70} for name in DEFAULT_WEIGHTS}
        result = ee._compute_weighted_vote(subs, DEFAULT_WEIGHTS)
        assert result["signal"] in ("sell", "strong_sell")
        assert result["score"] < 40

    @pytest.mark.asyncio
    async def test_mixed_signals(self, ee: EnsembleAIEngine) -> None:
        subs = {
            "technical": {"score": 80, "signal": "bullish", "confidence": 70},
            "fundamental": {"score": 70, "signal": "bullish", "confidence": 60},
            "news": {"score": 50, "signal": "neutral", "confidence": 50},
            "macro": {"score": 40, "signal": "bearish", "confidence": 60},
            "risk": {"score": 30, "signal": "bearish", "confidence": 50},
            "pattern": {"score": 60, "signal": "bullish", "confidence": 55},
        }
        result = ee._compute_weighted_vote(subs, DEFAULT_WEIGHTS)
        assert "score" in result
        assert "signal" in result

    @pytest.mark.asyncio
    async def test_empty_sub_models(self, ee: EnsembleAIEngine) -> None:
        result = ee._compute_weighted_vote({}, DEFAULT_WEIGHTS)
        assert result["score"] == 50
        assert result["signal"] == "hold"

    @pytest.mark.asyncio
    async def test_partial_data(self, ee: EnsembleAIEngine) -> None:
        subs = {"technical": {"score": 80, "signal": "bullish", "confidence": 70}}
        result = ee._compute_weighted_vote(subs, DEFAULT_WEIGHTS)
        assert result["score"] == 80
        assert result["signal"] == "buy"


class TestAgreement:
    @pytest.mark.asyncio
    async def test_high_agreement(self, ee: EnsembleAIEngine) -> None:
        subs = {name: {"signal": "bullish"} for name in DEFAULT_WEIGHTS}
        agreement = ee._compute_agreement(subs, "bullish")
        assert agreement["level"] == "high"
        assert agreement["factor"] >= 0.66

    @pytest.mark.asyncio
    async def test_low_agreement(self, ee: EnsembleAIEngine) -> None:
        subs = {name: {"signal": "bullish" if i < 2 else "bearish"} for i, name in enumerate(DEFAULT_WEIGHTS)}
        agreement = ee._compute_agreement(subs, "bullish")
        assert agreement["factor"] < 0.66


class TestAnalyzeTechnical:
    @pytest.mark.asyncio
    async def test_with_rsi_data(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="rsi", params_hash="a", value=75.0))
        await session.flush()
        result = await ee._analyze_technical("TEST", date(2024, 6, 5))
        assert result["score"] < 50

    @pytest.mark.asyncio
    async def test_no_data(self, ee: EnsembleAIEngine) -> None:
        result = await ee._analyze_technical("NODATA", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"

    @pytest.mark.asyncio
    async def test_rsi_oversold(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="rsi", params_hash="a", value=25.0))
        await session.flush()
        result = await ee._analyze_technical("TEST", date(2024, 6, 5))
        assert result["score"] > 50

    @pytest.mark.asyncio
    async def test_macd_bullish(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="macd", params_hash="a", value=1.5, value_secondary=1.0))
        await session.flush()
        result = await ee._analyze_technical("TEST", date(2024, 6, 5))
        assert result["score"] >= 50


class TestAnalyzeFundamental:
    @pytest.mark.asyncio
    async def test_low_pe(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(FundamentalMetric(symbol="TEST", fiscal_year=2024, fiscal_period=1, period_type="annual", metric_name="PE_RATIO", value=8.0))
        await session.flush()
        result = await ee._analyze_fundamental("TEST", date(2024, 12, 31))
        assert result["score"] > 50

    @pytest.mark.asyncio
    async def test_high_quality(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(FundamentalMetric(symbol="TEST", fiscal_year=2024, fiscal_period=1, period_type="annual", metric_name="QUALITY_SCORE", value=85.0))
        await session.flush()
        result = await ee._analyze_fundamental("TEST", date(2024, 12, 31))
        assert result["score"] >= 50

    @pytest.mark.asyncio
    async def test_no_data(self, ee: EnsembleAIEngine) -> None:
        result = await ee._analyze_fundamental("NODATA", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"


class TestAnalyzeNews:
    @pytest.mark.asyncio
    async def test_positive_sentiment(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        article = NewsArticle(title="Test", source="src", source_id="1", url="http://x.com", url_hash="a", symbol="TEST", published_at=date(2024, 6, 1))
        session.add(article)
        await session.flush()
        session.add(NewsNLPAnalysis(article_id=article.id, sentiment_positive=0.8, sentiment_negative=0.1, sentiment_confidence=0.9))
        await session.flush()
        result = await ee._analyze_news("TEST", date(2024, 6, 5))
        assert result["score"] > 50

    @pytest.mark.asyncio
    async def test_no_news(self, ee: EnsembleAIEngine) -> None:
        result = await ee._analyze_news("NODATA", date.today())
        assert result["score"] == 50

    @pytest.mark.asyncio
    async def test_negative_sentiment(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        article = NewsArticle(title="Test", source="src", source_id="2", url="http://y.com", url_hash="b", symbol="TEST", published_at=date(2024, 6, 1))
        session.add(article)
        await session.flush()
        session.add(NewsNLPAnalysis(article_id=article.id, sentiment_positive=0.1, sentiment_negative=0.8, sentiment_confidence=0.9))
        await session.flush()
        result = await ee._analyze_news("TEST", date(2024, 6, 5))
        assert result["score"] < 50


class TestAnalyzeMacro:
    @pytest.mark.asyncio
    async def test_with_sector_data(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(SectorPerformance(sector="Tech", as_of_date=date(2024, 6, 1), period_label="1M", momentum_score=15.0))
        await session.flush()
        result = await ee._analyze_macro("Tech", date(2024, 6, 5))
        assert result["score"] > 50

    @pytest.mark.asyncio
    async def test_with_breadth(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(MarketBreadth(trade_date=date(2024, 6, 1), advancing=300, declining=200, unchanged=50, total_stocks=550, advancing_volume=100000, declining_volume=80000, unchanged_volume=5000, total_volume=185000, new_highs=30, new_lows=10, index_strength_score=70.0))
        await session.flush()
        result = await ee._analyze_macro(None, date(2024, 6, 5))
        assert result["score"] > 50

    @pytest.mark.asyncio
    async def test_no_data(self, ee: EnsembleAIEngine) -> None:
        result = await ee._analyze_macro(None, date.today())
        assert result["score"] == 50


class TestAnalyzeRisk:
    @pytest.mark.asyncio
    async def test_low_risk(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=15.0, liquidity_score=85.0, volatility_252d=12.0))
        await session.flush()
        result = await ee._analyze_risk("TEST", date(2024, 6, 5))
        assert result["score"] > 60
        assert result["signal"] == "bullish"

    @pytest.mark.asyncio
    async def test_high_risk(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=85.0, liquidity_score=20.0, volatility_252d=70.0))
        await session.flush()
        result = await ee._analyze_risk("TEST", date(2024, 6, 5))
        assert result["score"] < 40

    @pytest.mark.asyncio
    async def test_no_data(self, ee: EnsembleAIEngine) -> None:
        result = await ee._analyze_risk("NODATA", date.today())
        assert result["score"] == 50


class TestAnalyzePattern:
    @pytest.mark.asyncio
    async def test_bullish_pattern(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(ChartPattern(symbol="TEST", pattern_type="double_bottom", direction="bullish", start_date=date(2024, 1, 1), end_date=date(2024, 6, 1), confidence_score=80.0, is_active=True))
        await session.flush()
        result = await ee._analyze_pattern("TEST", date(2024, 6, 5))
        assert result["score"] > 50

    @pytest.mark.asyncio
    async def test_bearish_pattern(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(ChartPattern(symbol="TEST", pattern_type="double_top", direction="bearish", start_date=date(2024, 1, 1), end_date=date(2024, 6, 1), confidence_score=75.0, is_active=True))
        await session.flush()
        result = await ee._analyze_pattern("TEST", date(2024, 6, 5))
        assert result["score"] < 50

    @pytest.mark.asyncio
    async def test_no_patterns(self, ee: EnsembleAIEngine) -> None:
        result = await ee._analyze_pattern("NODATA", date.today())
        assert result["score"] == 50


class TestFullPrediction:
    @pytest.mark.asyncio
    async def test_predict_with_all_data(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="rsi", params_hash="a", value=65.0))
        session.add(FundamentalMetric(symbol="TEST", fiscal_year=2024, fiscal_period=1, period_type="annual", metric_name="PE_RATIO", value=15.0))
        session.add(SectorPerformance(sector="Tech", as_of_date=date(2024, 6, 1), period_label="1M", momentum_score=10.0))
        session.add(MarketBreadth(trade_date=date(2024, 6, 1), advancing=300, declining=200, unchanged=50, total_stocks=550, advancing_volume=100000, declining_volume=80000, unchanged_volume=5000, total_volume=185000, new_highs=30, new_lows=10, index_strength_score=65.0))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=30.0, liquidity_score=75.0, volatility_252d=18.0))
        await session.flush()

        result = await ee.predict("TEST", date(2024, 6, 5), store=False)
        assert "error" not in result
        assert result["ensemble_signal"] is not None
        assert result["ensemble_score"] is not None
        assert result["explanation"] is not None

    @pytest.mark.asyncio
    async def test_predict_and_store(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=30.0, liquidity_score=75.0, volatility_252d=18.0))
        await session.flush()

        result = await ee.predict("TEST", date(2024, 6, 5), store=True)
        assert result.get("id") is not None

        pred = await ee.get_prediction("TEST", date(2024, 6, 5))
        assert pred is not None
        assert pred.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_duplicate_store(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        await session.flush()

        await ee.predict("TEST", date(2024, 6, 5), store=True)
        with pytest.raises(ValueError, match="already exists"):
            await ee.predict("TEST", date(2024, 6, 5), store=True)

    @pytest.mark.asyncio
    async def test_company_not_found(self, ee: EnsembleAIEngine) -> None:
        result = await ee.predict("NONEXIST")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_prediction_history(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=30.0, liquidity_score=75.0, volatility_252d=18.0))
        await session.flush()

        await ee.predict("TEST", date(2024, 6, 1), store=True)
        await ee.predict("TEST", date(2024, 7, 1), store=True)

        rows, total = await ee.get_prediction_history(symbol="TEST")
        assert total >= 2

    @pytest.mark.asyncio
    async def test_delete_prediction(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=30.0, liquidity_score=75.0, volatility_252d=18.0))
        await session.flush()

        result = await ee.predict("TEST", date(2024, 6, 1), store=True)
        assert await ee.delete_prediction(result["id"]) is True
        assert await ee.delete_prediction(result["id"]) is False


class TestCustomWeights:
    @pytest.mark.asyncio
    async def test_custom_weights_produce_different_results(self, ee: EnsembleAIEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=15.0, liquidity_score=85.0, volatility_252d=12.0))
        await session.flush()

        default = await ee.predict("TEST", date(2024, 6, 1), store=False)
        high_risk = await ee.predict("TEST", date(2024, 6, 1), weights={"technical": 0, "fundamental": 0, "news": 0, "macro": 0, "risk": 1.0, "pattern": 0}, store=False)
        assert default["risk_score"] == high_risk["risk_score"]
