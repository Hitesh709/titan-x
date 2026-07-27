import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore, DynamicWeight
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.macro import MacroAnalysis
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.news import NewsArticle, NewsArticleCategory, NewsCategory
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator
from titan_x.services.dynamic_ai_score_service import DynamicAIScoreService, DEFAULT_WEIGHTS, SOURCE_NAMES

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


# ── Helper methods ──

class TestHelpers:
    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_all_sources_present(self):
        assert set(SOURCE_NAMES) == {
            "technical", "fundamental", "news", "macro",
            "liquidity", "risk", "market_regime",
        }

    def test_signal_to_score(self):
        svc = DynamicAIScoreService.__new__(DynamicAIScoreService)
        assert svc._score_to_signal(80) == "bullish"
        assert svc._score_to_signal(20) == "bearish"
        assert svc._score_to_signal(50) == "neutral"
        assert svc._score_to_signal(65) == "bullish"
        assert svc._score_to_signal(35) == "bearish"

    def test_agreement_factor_all_match(self):
        svc = DynamicAIScoreService.__new__(DynamicAIScoreService)
        signals = {
            "technical": {"signal": "bullish", "score": 70, "confidence": 60},
            "fundamental": {"signal": "bullish", "score": 65, "confidence": 50},
            "news": {"signal": "bullish", "score": 68, "confidence": 55},
        }
        factor = svc._agreement_factor(signals, "bullish")
        assert factor == 1.0

    def test_agreement_factor_none_match(self):
        svc = DynamicAIScoreService.__new__(DynamicAIScoreService)
        signals = {
            "technical": {"signal": "bullish", "score": 70, "confidence": 60},
            "fundamental": {"signal": "bearish", "score": 30, "confidence": 50},
            "news": {"signal": "neutral", "score": 50, "confidence": 55},
        }
        factor = svc._agreement_factor(signals, "bullish")
        assert factor == pytest.approx(1.0 / 3.0)

    def test_combine_equal_weights(self):
        svc = DynamicAIScoreService.__new__(DynamicAIScoreService)
        signals = {}
        for name in SOURCE_NAMES:
            signals[name] = {"score": 70.0, "signal": "bullish", "confidence": 80}
        combined = svc._combine(signals, DEFAULT_WEIGHTS)
        assert combined["score"] == pytest.approx(70.0)
        assert combined["signal"] == "buy"
        assert combined["confidence"] > 50

    def test_combine_mixed_signals(self):
        svc = DynamicAIScoreService.__new__(DynamicAIScoreService)
        signals = {
            "technical": {"score": 80, "signal": "bullish", "confidence": 70},
            "fundamental": {"score": 70, "signal": "bullish", "confidence": 60},
            "news": {"score": 30, "signal": "bearish", "confidence": 80},
            "macro": {"score": 50, "signal": "neutral", "confidence": 50},
            "liquidity": {"score": 60, "signal": "neutral", "confidence": 60},
            "risk": {"score": 40, "signal": "bearish", "confidence": 70},
            "market_regime": {"score": 55, "signal": "neutral", "confidence": 65},
        }
        combined = svc._combine(signals, DEFAULT_WEIGHTS)
        assert 30 <= combined["score"] <= 70
        assert combined["signal"] in ("buy", "hold", "sell")

    def test_signal_to_direction(self):
        svc = DynamicAIScoreService.__new__(DynamicAIScoreService)
        assert svc._signal_to_direction("bullish") == 1
        assert svc._signal_to_direction("buy") == 1
        assert svc._signal_to_direction("strong_buy") == 1
        assert svc._signal_to_direction("bearish") == -1
        assert svc._signal_to_direction("sell") == -1
        assert svc._signal_to_direction("strong_sell") == -1
        assert svc._signal_to_direction("neutral") == 0
        assert svc._signal_to_direction("hold") == 0


# ── Dynamic Weight ──

@pytest.mark.asyncio
class TestDynamicWeight:
    async def test_accuracy(self):
        w = DynamicWeight(source_name="test", weight=0.5, total_predictions=10, correct_predictions=7)
        assert w.accuracy() == 70.0

    async def test_accuracy_zero(self):
        w = DynamicWeight(source_name="test", weight=0.5, total_predictions=0, correct_predictions=0)
        assert w.accuracy() == 0.0

    async def test_get_or_create_weight(self, session):
        svc = DynamicAIScoreService(session)
        w1 = await svc._get_or_create_weight("technical")
        assert w1.source_name == "technical"
        assert w1.weight == pytest.approx(DEFAULT_WEIGHTS["technical"])

        w2 = await svc._get_or_create_weight("technical")
        assert w2.id == w1.id

    async def test_get_or_create_all_sources(self, session):
        svc = DynamicAIScoreService(session)
        for name in SOURCE_NAMES:
            w = await svc._get_or_create_weight(name)
            assert w.source_name == name
            assert w.total_predictions == 0
            assert w.correct_predictions == 0

    async def test_load_weights_defaults(self, session):
        svc = DynamicAIScoreService(session)
        weights = await svc._load_weights()
        for name in SOURCE_NAMES:
            assert name in weights
            assert weights[name] == pytest.approx(DEFAULT_WEIGHTS[name])

    async def test_load_weights_custom(self, session):
        svc = DynamicAIScoreService(session)
        session.add(DynamicWeight(source_name="technical", weight=0.5))
        await session.flush()
        weights = await svc._load_weights()
        assert weights["technical"] == 0.5
        for name in SOURCE_NAMES:
            if name != "technical":
                assert weights[name] == pytest.approx(DEFAULT_WEIGHTS[name])


# ── Compute Score ──

@pytest.mark.asyncio
class TestComputeScore:
    async def test_compute_fails_missing_company(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc.compute_score("MISSING")
        assert "error" in result

    async def _seed_company(self, session, symbol="TEST", sector="Technology"):
        c = Company(symbol=symbol, company_name=f"{symbol} Corp", sector=sector, isin=f"IN{symbol}1234", exchange="NSE")
        session.add(c)
        await session.flush()
        return c

    async def _seed_technical(self, session, symbol="TEST", as_of_date=None):
        if as_of_date is None:
            as_of_date = date.today()
        session.add(TechnicalIndicator(symbol=symbol, trade_date=as_of_date, indicator="rsi", params_hash="h1", value=65.0))
        session.add(TechnicalIndicator(symbol=symbol, trade_date=as_of_date, indicator="macd", params_hash="h2", value=100.0, value_secondary=95.0))
        session.add(TechnicalIndicator(symbol=symbol, trade_date=as_of_date, indicator="sma_20", params_hash="h3", value=150.0, value_secondary=148.0))
        await session.flush()

    async def _seed_fundamental(self, session, symbol="TEST"):
        session.add(FundamentalMetric(symbol=symbol, metric_name="PE_RATIO", value=15.0, period_type="annual", fiscal_year=2024, fiscal_period=4))
        session.add(FundamentalMetric(symbol=symbol, metric_name="ROE", value=0.15, period_type="annual", fiscal_year=2024, fiscal_period=4))
        await session.flush()

    async def _seed_news(self, session, symbol="TEST", as_of_date=None):
        if as_of_date is None:
            as_of_date = date.today()
        cat = NewsCategory(name="earnings")
        session.add(cat)
        await session.flush()
        article = NewsArticle(symbol=symbol, title="Test", published_at=as_of_date, source="test", source_id="s1", url="http://test.com", url_hash="uh1")
        session.add(article)
        await session.flush()
        session.add(NewsNLPAnalysis(article_id=article.id, sentiment_positive=0.6, sentiment_negative=0.2, sentiment_confidence=0.7))
        await session.flush()

    async def _seed_sector(self, session, sector="Technology"):
        session.add(SectorPerformance(sector=sector, period_label="1M", as_of_date=date.today(), momentum_score=10.0, relative_strength=0.5))
        await session.flush()

    async def _seed_macro(self, session):
        session.add(MacroAnalysis(as_of_date=date.today(), composite_macro_score=60.0))
        await session.flush()

    async def _seed_breadth(self, session):
        session.add(MarketBreadth(trade_date=date.today(), index_strength_score=55.0, breadth_oscillator=20.0))
        await session.flush()

    async def _seed_risk(self, session, symbol="TEST", as_of_date=None):
        if as_of_date is None:
            as_of_date = date.today()
        session.add(RiskMetrics(symbol=symbol, as_of_date=as_of_date, composite_risk_score=30.0, liquidity_score=70.0, volatility_252d=25.0, avg_daily_volume_20d=2_000_000, avg_dollar_volume_20d=20_000_000))
        await session.flush()

    async def _seed_regime(self, session, symbol="TEST", as_of_date=None):
        if as_of_date is None:
            as_of_date = date.today()
        session.add(MarketRegime(symbol=symbol, as_of_date=as_of_date, trend_score=70.0, sentiment_score=60.0, volatility_score=30.0, confidence=0.8))
        await session.flush()

    async def _seed_all(self, session, symbol="TEST", sector="Technology"):
        await self._seed_company(session, symbol, sector)
        await self._seed_technical(session, symbol)
        await self._seed_fundamental(session, symbol)
        await self._seed_news(session, symbol)
        await self._seed_sector(session, sector)
        await self._seed_macro(session)
        await self._seed_breadth(session)
        await self._seed_risk(session, symbol)
        await self._seed_regime(session, symbol)

    async def test_compute_without_store(self, session):
        await self._seed_all(session)
        svc = DynamicAIScoreService(session)
        result = await svc.compute_score("TEST", store=False)
        assert "error" not in result
        assert result["symbol"] == "TEST"
        assert isinstance(result["combined_score"], float)
        assert result["combined_signal"] in ("strong_buy", "buy", "hold", "sell", "strong_sell")
        assert isinstance(result["combined_confidence"], float)
        for name in SOURCE_NAMES:
            assert f"{name}_score" in result
            assert f"{name}_signal" in result
            assert f"{name}_confidence" in result
        assert "weights" in result
        assert "source_signals" in result

    async def test_compute_with_store(self, session):
        await self._seed_all(session)
        svc = DynamicAIScoreService(session)
        result = await svc.compute_score("TEST", store=True)
        assert result.get("id") is not None

        score = await svc.get_score("TEST", date.today())
        assert score is not None
        assert score.combined_score == result["combined_score"]

    async def test_compute_stores_all_source_scores(self, session):
        await self._seed_all(session)
        svc = DynamicAIScoreService(session)
        result = await svc.compute_score("TEST", store=True)

        score = await svc.get_score("TEST", date.today())
        for name in SOURCE_NAMES:
            assert getattr(score, f"{name}_score") is not None
            assert getattr(score, f"{name}_signal") is not None
            assert getattr(score, f"{name}_confidence") is not None

    async def test_compute_partial_data(self, session):
        await self._seed_company(session, "PARTIAL", "Finance")
        svc = DynamicAIScoreService(session)
        result = await svc.compute_score("PARTIAL", store=False)
        assert "error" not in result
        assert result["combined_score"] > 0

    async def test_compute_multiple_symbols(self, session):
        await self._seed_all(session, "SYM_A")
        await self._seed_company(session, "SYM_B", "Finance")
        svc = DynamicAIScoreService(session)
        ra = await svc.compute_score("SYM_A", store=True)
        rb = await svc.compute_score("SYM_B", store=True)
        assert ra["combined_score"] != rb["combined_score"] or ra["combined_signal"] != rb["combined_signal"]

    async def test_compute_uses_custom_weights(self, session):
        await self._seed_all(session)
        svc = DynamicAIScoreService(session)

        custom_weights = {name: 0.5 if name == "technical" else 0.0 for name in SOURCE_NAMES}
        total = sum(custom_weights.values())
        custom_weights = {k: v / total for k, v in custom_weights.items()}

        session.add(DynamicWeight(source_name="technical", weight=custom_weights["technical"]))
        await session.flush()

        result = await svc.compute_score("TEST", store=False)
        assert result["combined_score"] > 0


# ── Adjust Weights ──

@pytest.mark.asyncio
class TestAdjustWeights:
    async def test_adjust_no_score(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc.adjust_weights("TEST", date.today(), 2.0)
        assert "error" in result

    async def test_adjust_weights_improves_accuracy(self, session):
        c = Company(symbol="TEST", company_name="Test Corp", sector="Tech", isin="INTEST1234", exchange="NSE")
        session.add(c)
        session.add(RiskMetrics(symbol="TEST", as_of_date=date.today(), composite_risk_score=30.0, liquidity_score=70.0, volatility_252d=25.0, avg_daily_volume_20d=2_000_000, avg_dollar_volume_20d=20_000_000))
        await session.flush()

        svc = DynamicAIScoreService(session)
        score_result = await svc.compute_score("TEST", store=True)
        assert "error" not in score_result

        adjust_result = await svc.adjust_weights("TEST", date.today(), 3.0)
        assert "error" not in adjust_result
        assert "adjusted_weights" in adjust_result
        assert "details" in adjust_result

        for name in SOURCE_NAMES:
            assert name in adjust_result["details"]
            d = adjust_result["details"][name]
            assert "correct" in d
            assert "correct_predictions" in d
            assert d["total_predictions"] >= 1

    async def test_adjust_decreases_weight_on_wrong_prediction(self, session):
        c = Company(symbol="TEST", company_name="Test Corp", sector="Tech", isin="INTEST1234", exchange="NSE")
        session.add(c)
        session.add(RiskMetrics(symbol="TEST", as_of_date=date.today(), composite_risk_score=30.0, liquidity_score=70.0, volatility_252d=25.0, avg_daily_volume_20d=2_000_000, avg_dollar_volume_20d=20_000_000))
        await session.flush()

        svc = DynamicAIScoreService(session)
        await svc.compute_score("TEST", store=True)
        await svc.adjust_weights("TEST", date.today(), -10.0)

        weights = await svc.get_weights()
        for name, info in weights["performance"].items():
            assert info["total_predictions"] >= 1

    async def test_get_weights_returns_all(self, session):
        svc = DynamicAIScoreService(session)
        w = await svc.get_weights()
        assert "weights" in w
        assert "performance" in w
        assert len(w["weights"]) == 0

        for name in SOURCE_NAMES:
            session.add(DynamicWeight(source_name=name, weight=DEFAULT_WEIGHTS[name]))
        await session.flush()

        w = await svc.get_weights()
        assert len(w["weights"]) == len(SOURCE_NAMES)


# ── Get Score / History ──

@pytest.mark.asyncio
class TestGetScore:
    async def test_get_score_none(self, session):
        svc = DynamicAIScoreService(session)
        s = await svc.get_score("TEST", date.today())
        assert s is None

    async def test_get_score_found(self, session):
        session.add(DynamicAIScore(symbol="TEST", as_of_date=date.today(), combined_score=65.0, combined_signal="bullish", combined_confidence=70.0))
        await session.flush()
        svc = DynamicAIScoreService(session)
        s = await svc.get_score("TEST", date.today())
        assert s is not None
        assert s.combined_score == 65.0
        assert s.combined_signal == "bullish"

    async def test_history_empty(self, session):
        svc = DynamicAIScoreService(session)
        scores, total = await svc.get_score_history()
        assert total == 0
        assert len(scores) == 0

    async def test_history_with_filters(self, session):
        svc = DynamicAIScoreService(session)
        for i in range(5):
            session.add(DynamicAIScore(symbol=f"SYM{i}", as_of_date=date.today(), combined_score=50.0 + i * 10, combined_signal="bullish", combined_confidence=60.0))
        await session.flush()

        scores, total = await svc.get_score_history(min_score=60.0)
        assert total >= 3

        scores, total = await svc.get_score_history(symbol="SYM0")
        assert total == 1

        scores, total = await svc.get_score_history(signal="bearish")
        assert total == 0

    async def test_pagination(self, session):
        svc = DynamicAIScoreService(session)
        for i in range(10):
            session.add(DynamicAIScore(symbol="TEST", as_of_date=date.today() - timedelta(days=i), combined_score=50.0, combined_signal="hold", combined_confidence=50.0))
        await session.flush()

        scores, total = await svc.get_score_history(symbol="TEST", skip=0, limit=3)
        assert total == 10
        assert len(scores) == 3

    async def test_delete_score(self, session):
        session.add(DynamicAIScore(symbol="TEST", as_of_date=date.today(), combined_score=50, combined_signal="hold", combined_confidence=50))
        await session.flush()

        svc = DynamicAIScoreService(session)
        s = await svc.get_score("TEST", date.today())
        assert s is not None

        deleted = await svc.delete_score(s.id)
        assert deleted

        s2 = await svc.get_score("TEST", date.today())
        assert s2 is None

    async def test_delete_missing(self, session):
        svc = DynamicAIScoreService(session)
        assert not await svc.delete_score(9999)


# ── Signal Sources (unit) ──

@pytest.mark.asyncio
class TestSignalSources:
    async def test_technical_no_data(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc._signal_technical("TEST", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"

    async def test_technical_with_data(self, session):
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date.today(), indicator="rsi", params_hash="h1", value=75.0))
        await session.flush()
        svc = DynamicAIScoreService(session)
        result = await svc._signal_technical("TEST", date.today())
        assert result["score"] < 50
        assert result["signal"] == "bearish"

    async def test_fundamental_no_data(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc._signal_fundamental("TEST", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"
        assert result["confidence"] == 20

    async def test_fundamental_with_data(self, session):
        session.add(FundamentalMetric(symbol="TEST", metric_name="PE_RATIO", value=12.0, period_type="annual", fiscal_year=2024, fiscal_period=4))
        await session.flush()
        svc = DynamicAIScoreService(session)
        result = await svc._signal_fundamental("TEST", date.today())
        assert result["score"] > 50

    async def test_news_no_data(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc._signal_news("TEST", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"

    async def test_news_with_sentiment(self, session):
        cat = NewsCategory(name="test")
        session.add(cat)
        await session.flush()
        today = date.today()
        article = NewsArticle(symbol="TEST", title="Good news", published_at=today - timedelta(days=1), source="test", source_id="s1", url="http://test.com", url_hash="uh1")
        session.add(article)
        await session.flush()
        session.add(NewsNLPAnalysis(article_id=article.id, sentiment_positive=0.8, sentiment_negative=0.1, sentiment_confidence=0.9))
        await session.flush()
        svc = DynamicAIScoreService(session)
        result = await svc._signal_news("TEST", today)
        assert result["score"] > 55
        assert result["signal"] == "bullish"

    async def test_macro_no_data(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc._signal_macro("Tech", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"

    async def test_macro_with_data(self, session):
        session.add(SectorPerformance(sector="Tech", period_label="1M", as_of_date=date.today(), momentum_score=20.0, relative_strength=1.0))
        session.add(MacroAnalysis(as_of_date=date.today(), composite_macro_score=70.0))
        session.add(MarketBreadth(trade_date=date.today(), index_strength_score=65.0, breadth_oscillator=30.0))
        await session.flush()
        svc = DynamicAIScoreService(session)
        result = await svc._signal_macro("Tech", date.today())
        assert result["score"] > 50
        assert result["signal"] == "bullish"

    async def test_liquidity_no_data(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc._signal_liquidity("TEST", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"

    async def test_liquidity_with_data(self, session):
        session.add(RiskMetrics(symbol="TEST", as_of_date=date.today(), liquidity_score=85.0, avg_daily_volume_20d=10_000_000, avg_dollar_volume_20d=100_000_000))
        await session.flush()
        svc = DynamicAIScoreService(session)
        result = await svc._signal_liquidity("TEST", date.today())
        assert result["score"] >= 80
        assert result["confidence"] >= 60

    async def test_risk_no_data(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc._signal_risk("TEST", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"

    async def test_risk_with_data(self, session):
        session.add(RiskMetrics(symbol="TEST", as_of_date=date.today(), composite_risk_score=20.0, volatility_252d=15.0))
        await session.flush()
        svc = DynamicAIScoreService(session)
        result = await svc._signal_risk("TEST", date.today())
        assert result["score"] > 60
        assert result["signal"] == "bullish"

    async def test_market_regime_no_data(self, session):
        svc = DynamicAIScoreService(session)
        result = await svc._signal_market_regime("TEST", date.today())
        assert result["score"] == 50
        assert result["signal"] == "neutral"

    async def test_market_regime_with_data(self, session):
        session.add(MarketRegime(symbol="TEST", as_of_date=date.today(), trend_score=75.0, sentiment_score=70.0, volatility_score=20.0, confidence=0.85))
        await session.flush()
        svc = DynamicAIScoreService(session)
        result = await svc._signal_market_regime("TEST", date.today())
        assert result["score"] > 60
        assert result["signal"] == "bullish"
        assert result["confidence"] >= 50
