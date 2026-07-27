from datetime import date, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.technical import TechnicalIndicator
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.explainability import ExplainabilityAnalysis
from titan_x.models.decision import TradingDecision
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.prediction import Prediction
from titan_x.services.explainability_engine import ExplainabilityEngine


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
async def ee(session: AsyncSession) -> ExplainabilityEngine:
    return ExplainabilityEngine(session)


class TestWhyBuy:
    def _call(self, ee: ExplainabilityEngine, **overrides) -> list:
        defaults = dict(prediction=None, decision=None, ensemble=None, technical={},
                        patterns=[], risk=None, fundamentals=[], similarities=[],
                        sector_data=None, breadth=None, latest_price=None)
        defaults.update(overrides)
        return ee._build_why_buy(**defaults)

    @pytest.mark.asyncio
    async def test_positive_decision(self, ee: ExplainabilityEngine) -> None:
        decision = type("", (), {"recommendation": "buy", "opportunity_score": 80, "confidence_score": 75})()
        factors = self._call(ee, decision=decision)
        assert len(factors) > 0
        assert any(f.impact == "positive" for f in factors)

    @pytest.mark.asyncio
    async def test_sell_decision_yields_no_buy_factors(self, ee: ExplainabilityEngine) -> None:
        decision = type("", (), {"recommendation": "sell", "opportunity_score": 30, "confidence_score": 60})()
        factors = self._call(ee, decision=decision)
        assert not any(f.source == "decision" for f in factors)

    @pytest.mark.asyncio
    async def test_prediction_bullish(self, ee: ExplainabilityEngine) -> None:
        decision = type("", (), {"recommendation": "buy", "opportunity_score": 70, "confidence_score": 70})()
        prediction = type("", (), {"overall_signal": "buy", "overall_confidence": 75})()
        factors = self._call(ee, decision=decision, prediction=prediction)
        assert len(factors) >= 2

    @pytest.mark.asyncio
    async def test_ensemble_bullish(self, ee: ExplainabilityEngine) -> None:
        ensemble = type("", (), {"ensemble_signal": "strong_buy", "ensemble_score": 85, "agreement_level": "high"})()
        factors = self._call(ee, ensemble=ensemble)
        assert any(f.source == "ensemble" for f in factors)

    @pytest.mark.asyncio
    async def test_tech_bullish_crossover(self, ee: ExplainabilityEngine) -> None:
        tech = {
            "sma_20": type("", (), {"value": 110, "value_secondary": None})(),
            "sma_50": type("", (), {"value": 100, "value_secondary": None})(),
        }
        factors = self._call(ee, technical=tech)
        assert any(f.source == "technical" for f in factors)

    @pytest.mark.asyncio
    async def test_pattern_bullish(self, ee: ExplainabilityEngine) -> None:
        patterns = [type("", (), {"is_active": True, "confidence_score": 80, "direction": "bullish", "pattern_type": "cup_and_handle", "target_price": 120})()]
        factors = self._call(ee, patterns=patterns)
        assert any(f.source == "pattern" for f in factors)

    @pytest.mark.asyncio
    async def test_low_risk_added(self, ee: ExplainabilityEngine) -> None:
        risk = type("", (), {"composite_risk_score": 25, "volatility_252d": 15, "liquidity_score": 85, "max_drawdown_1y": 8, "event_risk_score": 2})()
        factors = self._call(ee, risk=risk)
        assert any(f.source == "risk" for f in factors)

    @pytest.mark.asyncio
    async def test_sector_positive(self, ee: ExplainabilityEngine) -> None:
        sector_data = {"momentum_score": 8.0, "relative_strength": 60.0}
        factors = self._call(ee, sector_data=sector_data)
        assert any(f.source == "sector" for f in factors)

    @pytest.mark.asyncio
    async def test_breadth_positive(self, ee: ExplainabilityEngine) -> None:
        breadth = {"index_strength_score": 70, "adv_decl_ratio": 1.5}
        factors = self._call(ee, breadth=breadth)
        assert any(f.source == "breadth" for f in factors)

    @pytest.mark.asyncio
    async def test_fundamental_bullish(self, ee: ExplainabilityEngine) -> None:
        fundamentals = [type("", (), {"metric_name": "PE_RATIO", "value": 10.0})()]
        factors = self._call(ee, fundamentals=fundamentals)
        assert any(f.source == "fundamental" for f in factors)

    @pytest.mark.asyncio
    async def test_similarity_positive(self, ee: ExplainabilityEngine) -> None:
        sims = [type("", (), {"avg_similarity": 75, "avg_return_5d": 3.0, "avg_return_10d": 5.0, "avg_return_20d": 8.0, "avg_return_60d": 12.0, "optimal_holding_period": 10, "max_matches": 50})()]
        factors = self._call(ee, similarities=sims)
        assert any(f.source == "similarity" for f in factors)

    @pytest.mark.asyncio
    async def test_latest_price(self, ee: ExplainabilityEngine) -> None:
        latest_price = type("", (), {"close": 105.5})()
        factors = self._call(ee, latest_price=latest_price)
        assert any(f.source == "price" for f in factors)


class TestWhyNotBuy:
    @pytest.mark.asyncio
    async def test_sell_decision(self, ee: ExplainabilityEngine) -> None:
        decision = type("", (), {"recommendation": "sell", "opportunity_score": 30, "confidence_score": 80})()
        factors = ee._build_why_not_buy(None, decision, None, {}, [], None, [], [], None, None)
        assert any(f.source == "decision" for f in factors)

    @pytest.mark.asyncio
    async def test_prediction_bearish(self, ee: ExplainabilityEngine) -> None:
        prediction = type("", (), {"overall_signal": "sell", "overall_confidence": 75})()
        factors = ee._build_why_not_buy(prediction, None, None, {}, [], None, [], [], None, None)
        assert any(f.source == "prediction" for f in factors)

    @pytest.mark.asyncio
    async def test_ensemble_bearish(self, ee: ExplainabilityEngine) -> None:
        ensemble = type("", (), {"ensemble_signal": "sell", "ensemble_score": 70, "agreement_level": "medium"})()
        factors = ee._build_why_not_buy(None, None, ensemble, {}, [], None, [], [], None, None)
        assert any(f.source == "ensemble" for f in factors)

    @pytest.mark.asyncio
    async def test_buy_decision_no_factors(self, ee: ExplainabilityEngine) -> None:
        decision = type("", (), {"recommendation": "buy", "opportunity_score": 80, "confidence_score": 70})()
        factors = ee._build_why_not_buy(None, decision, None, {}, [], None, [], [], None, None)
        assert not any(f.source == "decision" for f in factors)


class TestStrengths:
    @pytest.mark.asyncio
    async def test_high_quality(self, ee: ExplainabilityEngine) -> None:
        fundamentals = [type("", (), {"metric_name": "QUALITY_SCORE", "value": 8.0})()]
        factors = ee._build_strengths({}, fundamentals, [], None, None, None)
        assert any(f.source == "fundamental" for f in factors)

    @pytest.mark.asyncio
    async def test_strong_roe(self, ee: ExplainabilityEngine) -> None:
        fundamentals = [type("", (), {"metric_name": "ROE", "value": 22.0})()]
        factors = ee._build_strengths({}, fundamentals, [], None, None, None)
        assert any(f.source == "fundamental" for f in factors)

    @pytest.mark.asyncio
    async def test_rsi_neutral(self, ee: ExplainabilityEngine) -> None:
        tech = {"rsi": type("", (), {"value": 50, "value_secondary": None})()}
        factors = ee._build_strengths(tech, [], [], None, None, None)
        assert any(f.source == "technical" for f in factors)

    @pytest.mark.asyncio
    async def test_ema_above_sma(self, ee: ExplainabilityEngine) -> None:
        tech = {
            "ema_12": type("", (), {"value": 110, "value_secondary": None})(),
            "sma_50": type("", (), {"value": 105, "value_secondary": None})(),
        }
        factors = ee._build_strengths(tech, [], [], None, None, None)
        assert any(f.source == "technical" for f in factors)

    @pytest.mark.asyncio
    async def test_sector_relative_strength(self, ee: ExplainabilityEngine) -> None:
        sector_data = {"momentum_score": 5, "relative_strength": 65}
        factors = ee._build_strengths({}, [], [], sector_data, None, None)
        assert any(f.source == "sector" for f in factors)

    @pytest.mark.asyncio
    async def test_breadth_positive(self, ee: ExplainabilityEngine) -> None:
        breadth = {"index_strength_score": 70, "adv_decl_ratio": 1.5}
        factors = ee._build_strengths({}, [], [], None, breadth, None)
        assert any(f.source == "breadth" for f in factors)

    @pytest.mark.asyncio
    async def test_high_liquidity(self, ee: ExplainabilityEngine) -> None:
        risk = type("", (), {"liquidity_score": 85, "composite_risk_score": 30, "volatility_252d": 20, "max_drawdown_1y": 8, "event_risk_score": 2})()
        factors = ee._build_strengths({}, [], [], None, None, risk)
        assert any(f.source == "risk" for f in factors)


class TestWeaknesses:
    @pytest.mark.asyncio
    async def test_low_quality(self, ee: ExplainabilityEngine) -> None:
        fundamentals = [type("", (), {"metric_name": "QUALITY_SCORE", "value": 3.0})()]
        factors = ee._build_weaknesses({}, fundamentals, [], None, None, None)
        assert any(f.source == "fundamental" for f in factors)

    @pytest.mark.asyncio
    async def test_high_pe(self, ee: ExplainabilityEngine) -> None:
        fundamentals = [type("", (), {"metric_name": "PE_RATIO", "value": 40.0})()]
        factors = ee._build_weaknesses({}, fundamentals, [], None, None, None)
        assert any(f.source == "fundamental" for f in factors)

    @pytest.mark.asyncio
    async def test_rsi_overbought(self, ee: ExplainabilityEngine) -> None:
        tech = {"rsi": type("", (), {"value": 78, "value_secondary": None})()}
        factors = ee._build_weaknesses(tech, [], [], None, None, None)
        assert any(f.source == "technical" for f in factors)

    @pytest.mark.asyncio
    async def test_ema_below_sma(self, ee: ExplainabilityEngine) -> None:
        tech = {
            "ema_12": type("", (), {"value": 95, "value_secondary": None})(),
            "sma_50": type("", (), {"value": 100, "value_secondary": None})(),
        }
        factors = ee._build_weaknesses(tech, [], [], None, None, None)
        assert any(f.source == "technical" for f in factors)

    @pytest.mark.asyncio
    async def test_bearish_pattern(self, ee: ExplainabilityEngine) -> None:
        patterns = [type("", (), {"is_active": True, "confidence_score": 75, "direction": "bearish", "pattern_type": "head_and_shoulders"})()]
        factors = ee._build_weaknesses({}, [], patterns, None, None, None)
        assert any(f.source == "pattern" for f in factors)


class TestRiskFactors:
    @pytest.mark.asyncio
    async def test_high_risk(self, ee: ExplainabilityEngine) -> None:
        risk = type("", (), {"risk_rating": "high", "composite_risk_score": 75, "volatility_252d": 40,
                             "volatility_60d": 35, "max_drawdown_1y": 30, "max_drawdown_3m": 18,
                             "event_risk_score": 8, "liquidity_score": 30, "gap_frequency_20d": 0.2})()
        factors = ee._build_risk_factors(risk, {})
        assert len(factors) > 0

    @pytest.mark.asyncio
    async def test_low_risk(self, ee: ExplainabilityEngine) -> None:
        risk = type("", (), {"risk_rating": None, "composite_risk_score": 15, "volatility_252d": 12,
                             "volatility_60d": 10, "max_drawdown_1y": 5, "max_drawdown_3m": 3,
                             "event_risk_score": 1, "liquidity_score": 95, "gap_frequency_20d": 0.05})()
        factors = ee._build_risk_factors(risk, {})
        assert all(f.impact == "negative" for f in factors)

    @pytest.mark.asyncio
    async def test_none_risk(self, ee: ExplainabilityEngine) -> None:
        factors = ee._build_risk_factors(None, {})
        assert len(factors) == 1
        assert factors[0].source == "risk"


class TestHistoricalEvidence:
    @pytest.mark.asyncio
    async def test_with_similarity(self, ee: ExplainabilityEngine) -> None:
        sims = [type("", (), {"avg_similarity": 75, "avg_return_5d": 3.0, "avg_return_10d": 5.0,
                              "avg_return_20d": 8.0, "avg_return_60d": 12.0, "optimal_holding_period": 10,
                              "max_matches": 50})()]
        factors = ee._build_historical_evidence(sims, None, [], None)
        assert any(f.source == "similarity" for f in factors)

    @pytest.mark.asyncio
    async def test_empty_similarity(self, ee: ExplainabilityEngine) -> None:
        factors = ee._build_historical_evidence([], None, [], None)
        assert not any(f.source == "similarity" for f in factors)


class TestOverallScore:
    def _make_factor(self, score: float, impact: str, weight: str = "medium"):
        return type("", (), {"score": score, "impact": impact, "weight": weight})()

    @pytest.mark.asyncio
    async def test_strong_buy(self, ee: ExplainabilityEngine) -> None:
        wb = [self._make_factor(80, "positive", "high")]
        wnb = [self._make_factor(20, "negative", "medium")]
        st = [self._make_factor(75, "positive", "medium")]
        wk = [self._make_factor(25, "negative", "medium")]
        rf = [self._make_factor(15, "negative", "medium")]
        score = ee._compute_overall_score(wb, wnb, st, wk, rf)
        signal = ee._score_to_signal(score)
        assert signal == "strong_buy"
        assert score >= 70

    @pytest.mark.asyncio
    async def test_strong_sell(self, ee: ExplainabilityEngine) -> None:
        wb = [self._make_factor(20, "positive", "medium")]
        wnb = [self._make_factor(80, "negative", "high")]
        st = [self._make_factor(25, "positive", "medium")]
        wk = [self._make_factor(80, "negative", "medium")]
        rf = [self._make_factor(85, "negative", "high")]
        score = ee._compute_overall_score(wb, wnb, st, wk, rf)
        signal = ee._score_to_signal(score)
        assert signal == "strong_sell"
        assert score <= 30

    @pytest.mark.asyncio
    async def test_neutral(self, ee: ExplainabilityEngine) -> None:
        wb = [self._make_factor(50, "positive", "medium")]
        wnb = [self._make_factor(50, "negative", "medium")]
        st = [self._make_factor(50, "positive", "medium")]
        wk = [self._make_factor(50, "negative", "medium")]
        rf = [self._make_factor(50, "negative", "medium")]
        score = ee._compute_overall_score(wb, wnb, st, wk, rf)
        signal = ee._score_to_signal(score)
        assert signal == "hold"
        assert 40 <= score <= 60

    @pytest.mark.asyncio
    async def test_empty_sections(self, ee: ExplainabilityEngine) -> None:
        score = ee._compute_overall_score([], [], [], [], [])
        signal = ee._score_to_signal(score)
        assert signal == "hold"
        assert score == 50


class TestScoreToSignal:
    @pytest.mark.asyncio
    async def test_strong_buy(self, ee: ExplainabilityEngine) -> None:
        assert ee._score_to_signal(85) == "strong_buy"

    @pytest.mark.asyncio
    async def test_buy(self, ee: ExplainabilityEngine) -> None:
        assert ee._score_to_signal(65) == "buy"

    @pytest.mark.asyncio
    async def test_hold(self, ee: ExplainabilityEngine) -> None:
        assert ee._score_to_signal(50) == "hold"

    @pytest.mark.asyncio
    async def test_sell(self, ee: ExplainabilityEngine) -> None:
        assert ee._score_to_signal(35) == "sell"

    @pytest.mark.asyncio
    async def test_strong_sell(self, ee: ExplainabilityEngine) -> None:
        assert ee._score_to_signal(15) == "strong_sell"


class TestGetDataSources:
    @pytest.mark.asyncio
    async def test_get_company_found(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        await session.flush()
        company = await ee._get_company("TEST")
        assert company is not None
        assert company.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_get_company_not_found(self, ee: ExplainabilityEngine) -> None:
        company = await ee._get_company("NONEXIST")
        assert company is None

    @pytest.mark.asyncio
    async def test_get_latest_decision_no_data(self, ee: ExplainabilityEngine) -> None:
        decision = await ee._get_latest_decision("TEST")
        assert decision is None

    @pytest.mark.asyncio
    async def test_get_latest_decision_found(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(TradingDecision(symbol="TEST", as_of_date=date(2024, 6, 1), opportunity_score=80,
                                    confidence_score=75, recommendation="buy", metadata_json="{}"))
        await session.flush()
        decision = await ee._get_latest_decision("TEST")
        assert decision is not None
        assert decision.recommendation == "buy"

    @pytest.mark.asyncio
    async def test_get_risk_found(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=25, volatility_252d=22))
        await session.flush()
        risk = await ee._get_risk_metrics("TEST", date(2024, 6, 5))
        assert risk is not None
        assert risk.composite_risk_score == 25

    @pytest.mark.asyncio
    async def test_get_sector_no_sector(self, ee: ExplainabilityEngine) -> None:
        data = await ee._get_sector_data(None, date.today())
        assert data is None

    @pytest.mark.asyncio
    async def test_get_breadth_found(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(MarketBreadth(trade_date=date(2024, 6, 1), advancing=300, declining=200, unchanged=50,
                                   total_stocks=550, advancing_volume=100000, declining_volume=80000,
                                   unchanged_volume=5000, total_volume=185000, new_highs=30, new_lows=10,
                                   index_strength_score=65))
        await session.flush()
        data = await ee._get_market_breadth(date(2024, 6, 5))
        assert data is not None
        assert "index_strength_score" in data


class TestFullAnalysis:
    @pytest.mark.asyncio
    async def test_company_not_found(self, ee: ExplainabilityEngine) -> None:
        result = await ee.analyze("NONEXIST")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_analyze_returns_all_sections(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="rsi", params_hash="a", value=65))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="sma_20", params_hash="a", value=105))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="sma_50", params_hash="a", value=95))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="ema_12", params_hash="a", value=102))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=25, volatility_252d=22, liquidity_score=80, max_drawdown_1y=10, event_risk_score=3))
        await session.flush()

        result = await ee.analyze("TEST", date(2024, 6, 5), store=False)
        assert "error" not in result
        assert "why_buy" in result
        assert "why_not_buy" in result
        assert "strengths" in result
        assert "weaknesses" in result
        assert "risk_factors" in result
        assert "historical_evidence" in result
        assert result["overall_signal"] is not None
        assert result["overall_score"] is not None

    @pytest.mark.asyncio
    async def test_analyze_and_store(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        result = await ee.analyze("TEST", date(2024, 6, 5), store=True)
        assert result.get("id") is not None

        analysis = await ee.get_analysis("TEST")
        assert analysis is not None
        assert analysis.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_duplicate_store(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        await ee.analyze("TEST", date(2024, 6, 5), store=True)
        with pytest.raises(ValueError, match="already exists"):
            await ee.analyze("TEST", date(2024, 6, 5), store=True)

    @pytest.mark.asyncio
    async def test_analysis_history(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        await ee.analyze("TEST", date(2024, 6, 1), store=True)
        rows, total = await ee.get_analysis_history(symbol="TEST")
        assert total >= 1

    @pytest.mark.asyncio
    async def test_delete_analysis(self, ee: ExplainabilityEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        result = await ee.analyze("TEST", date(2024, 6, 1), store=True)
        assert await ee.delete_analysis(result["id"]) is True
        assert await ee.delete_analysis(result["id"]) is False
