from datetime import date, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.company import Company
from titan_x.models.decision import TradingDecision
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.explainability import ExplainabilityAnalysis
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.prediction import Prediction
from titan_x.models.price import DailyPrice
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator
from titan_x.services.explainability_dashboard_service import (
    ExplainabilityDashboardService,
    _signal_to_strength,
)


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
async def svc(session: AsyncSession) -> ExplainabilityDashboardService:
    return ExplainabilityDashboardService(session)


# ── Signal Strength ──

class TestSignalStrength:
    def test_strong_buy(self):
        assert _signal_to_strength("strong_buy") == 2

    def test_buy(self):
        assert _signal_to_strength("buy") == 1

    def test_hold(self):
        assert _signal_to_strength("hold") == 0

    def test_sell(self):
        assert _signal_to_strength("sell") == -1

    def test_strong_sell(self):
        assert _signal_to_strength("strong_sell") == -2

    def test_none(self):
        assert _signal_to_strength(None) == 0

    def test_case_insensitive(self):
        assert _signal_to_strength("STRONG_BUY") == 2
        assert _signal_to_strength("Buy") == 1

    def test_bullish_bearish(self):
        assert _signal_to_strength("bullish") == 1
        assert _signal_to_strength("bearish") == -1
        assert _signal_to_strength("neutral") == 0


# ── Feature Importance ──

class TestFeatureImportance:
    def test_empty_analysis(self, svc: ExplainabilityDashboardService):
        result = svc._compute_feature_importance({})
        assert result == []

    def test_ranks_by_score(self, svc: ExplainabilityDashboardService):
        analysis = {
            "why_buy": [
                {"factor": "Strong momentum", "score": 85, "impact": "positive", "source": "technical", "weight": "high"},
                {"factor": "Good fundamentals", "score": 70, "impact": "positive", "source": "fundamental", "weight": "medium"},
            ],
            "why_not_buy": [],
            "strengths": [],
            "weaknesses": [],
        }
        result = svc._compute_feature_importance(analysis)
        assert len(result) == 2
        assert result[0]["importance_score"] == 85
        assert result[1]["importance_score"] == 70

    def test_combines_all_sections(self, svc: ExplainabilityDashboardService):
        analysis = {
            "why_buy": [{"factor": "A", "score": 80, "impact": "positive", "source": "tech", "weight": "high"}],
            "why_not_buy": [{"factor": "B", "score": 60, "impact": "negative", "source": "risk", "weight": "medium"}],
            "strengths": [{"factor": "C", "score": 90, "impact": "positive", "source": "fundamental", "weight": "high"}],
            "weaknesses": [{"factor": "D", "score": 40, "impact": "negative", "source": "technical", "weight": "low"}],
        }
        result = svc._compute_feature_importance(analysis)
        assert len(result) == 4

    def test_includes_direction_source_weight(self, svc: ExplainabilityDashboardService):
        analysis = {
            "why_buy": [{"factor": "Test", "score": 75, "impact": "positive", "source": "test_source", "weight": "high"}],
            "why_not_buy": [], "strengths": [], "weaknesses": [],
        }
        result = svc._compute_feature_importance(analysis)
        assert result[0]["direction"] == "positive"
        assert result[0]["source"] == "test_source"
        assert result[0]["weight"] == "high"


# ── Model Agreement ──

class TestModelAgreement:
    def test_no_models(self, svc: ExplainabilityDashboardService):
        result = svc._compute_model_agreement(None, None, None, None)
        assert result["agreement_level"] == "unknown"
        assert result["total_models"] == 0

    def test_all_agree_buy(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("buy", 80)
        dec = _make_decision("buy", 75)
        ensemble = _make_ensemble("buy", 85, "high")
        result = svc._compute_model_agreement(pred, dec, ensemble, None)
        assert result["agreement_level"] == "high"
        assert result["dominant_signal"] == "buy"
        assert result["total_models"] == 3
        assert result["agreeing_models"] == 3

    def test_all_agree_sell(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("sell", 70)
        dec = _make_decision("sell", 65)
        result = svc._compute_model_agreement(pred, dec, None, None)
        assert result["agreement_level"] == "high"
        assert result["dominant_signal"] == "sell"

    def test_mixed_signals(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("buy", 80)
        dec = _make_decision("sell", 70)
        ensemble = _make_ensemble("hold", 50, "low")
        result = svc._compute_model_agreement(pred, dec, ensemble, None)
        assert result["total_models"] == 3
        assert result["agreeing_models"] == 1

    def test_medium_agreement(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("buy", 80)
        dec = _make_decision("buy", 75)
        ensemble = _make_ensemble("sell", 70, "medium")
        result = svc._compute_model_agreement(pred, dec, ensemble, None)
        assert result["agreement_level"] == "medium"
        assert result["dominant_signal"] == "buy"

    def test_includes_stored_analysis(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("buy", 80)
        stored = _make_stored("strong_buy", 90)
        result = svc._compute_model_agreement(pred, None, None, stored)
        assert result["total_models"] == 2
        assert result["dominant_signal"] == "buy"
        assert "overall_analysis" in result["signals"]


# ── Confidence Breakdown ──

class TestConfidenceBreakdown:
    def test_no_sources(self, svc: ExplainabilityDashboardService):
        result = svc._compute_confidence_breakdown(None, None, None, None, {})
        assert result["overall_confidence"] is None
        assert result["sources"] == []

    def test_single_source(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("buy", 80)
        result = svc._compute_confidence_breakdown(pred, None, None, None, {"overall_confidence": 75})
        assert result["overall_confidence"] == 75
        assert result["average_source_confidence"] == 80
        assert len(result["sources"]) == 1
        assert result["sources"][0]["source"] == "prediction"

    def test_multiple_sources(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("buy", 80)
        dec = _make_decision("buy", 70)
        ensemble = _make_ensemble("buy", 90, "high")
        result = svc._compute_confidence_breakdown(pred, dec, ensemble, None, {"overall_confidence": 85})
        assert len(result["sources"]) == 3
        assert result["average_source_confidence"] == 80

    def test_average_excludes_none(self, svc: ExplainabilityDashboardService):
        pred = _make_prediction("buy", 80)
        dec = _make_decision("buy", None)
        result = svc._compute_confidence_breakdown(pred, dec, None, None, {})
        assert result["average_source_confidence"] == 80
        assert len(result["sources"]) == 1


# ── Historical Analogues ──

@pytest.mark.asyncio
class TestHistoricalAnalogues:
    async def test_from_analysis_evidence(self, svc: ExplainabilityDashboardService):
        analysis = {
            "historical_evidence": [
                {"factor": "Similar period in 2023", "score": 75, "impact": "positive", "source": "similarity", "weight": "high"},
                {"factor": "Pattern match 85%", "score": 85, "impact": "positive", "source": "pattern", "weight": "medium"},
            ],
        }
        result = await svc._compute_historical_analogues(analysis, "TEST")
        assert len(result) >= 2
        assert result[0]["similarity_score"] >= result[1]["similarity_score"]

    async def test_with_db_similarity(self, svc: ExplainabilityDashboardService, session: AsyncSession):
        session.add(SimilarityAnalysis(
            symbol="TEST", query_start_date=date(2024, 1, 1), query_end_date=date(2024, 6, 1),
            window_days=60, lookback_days=365, min_similarity=70, total_matches=25,
            avg_similarity=80, avg_return_5d=3.5, avg_return_10d=6.0,
            avg_return_20d=10.0, avg_return_60d=15.0, max_matches=25, optimal_holding_period=12,
        ))
        await session.flush()
        result = await svc._compute_historical_analogues({"historical_evidence": []}, "TEST")
        assert len(result) == 1
        assert result[0]["source"] == "similarity_analysis"
        assert result[0]["avg_similarity"] == 80
        assert result[0]["avg_return_5d"] == 3.5

    async def test_empty(self, svc: ExplainabilityDashboardService):
        result = await svc._compute_historical_analogues({"historical_evidence": []}, "NONE")
        assert result == []


# ── Full Dashboard ──

@pytest.mark.asyncio
class TestFullDashboard:
    async def test_company_not_found(self, svc: ExplainabilityDashboardService):
        result = await svc.get_dashboard("NONEXIST")
        assert "error" in result

    async def test_dashboard_returns_all_sections(
        self, svc: ExplainabilityDashboardService, session: AsyncSession,
    ):
        await _seed_basic_data(session)
        result = await svc.get_dashboard("TEST", date(2024, 6, 5))
        assert "error" not in result
        assert result["symbol"] == "TEST"
        assert "overall" in result
        assert "feature_importance" in result
        assert "model_agreement" in result
        assert "confidence_breakdown" in result
        assert "risk_factors" in result
        assert "historical_analogues" in result

    async def test_overall_section(
        self, svc: ExplainabilityDashboardService, session: AsyncSession,
    ):
        await _seed_basic_data(session)
        result = await svc.get_dashboard("TEST", date(2024, 6, 5))
        overall = result["overall"]
        assert "score" in overall
        assert "signal" in overall
        assert "confidence" in overall

    async def test_feature_importance_ranked(
        self, svc: ExplainabilityDashboardService, session: AsyncSession,
    ):
        await _seed_basic_data(session)
        result = await svc.get_dashboard("TEST", date(2024, 6, 5))
        features = result["feature_importance"]
        assert len(features) > 0
        scores = [f["importance_score"] for f in features]
        assert scores == sorted(scores, reverse=True)

    async def test_model_agreement_with_data(
        self, svc: ExplainabilityDashboardService, session: AsyncSession,
    ):
        await _seed_basic_data(session)
        session.add(
            _make_prediction_db("TEST", date(2024, 6, 5), "buy", 80)
        )
        session.add(
            _make_decision_db("TEST", date(2024, 6, 5), "buy", 75)
        )
        session.add(
            _make_ensemble_db("TEST", date(2024, 6, 5), "buy", 85, "high")
        )
        await session.flush()
        result = await svc.get_dashboard("TEST", date(2024, 6, 5))
        agreement = result["model_agreement"]
        assert agreement["total_models"] >= 3
        assert agreement["dominant_signal"] in ("buy", "sell", "neutral")

    async def test_confidence_breakdown_with_data(
        self, svc: ExplainabilityDashboardService, session: AsyncSession,
    ):
        await _seed_basic_data(session)
        session.add(
            _make_prediction_db("TEST", date(2024, 6, 5), "buy", 80)
        )
        await session.flush()
        result = await svc.get_dashboard("TEST", date(2024, 6, 5))
        conf = result["confidence_breakdown"]
        assert "overall_confidence" in conf
        assert "average_source_confidence" in conf

    async def test_risk_factors_present(
        self, svc: ExplainabilityDashboardService, session: AsyncSession,
    ):
        await _seed_basic_data(session)
        result = await svc.get_dashboard("TEST", date(2024, 6, 5))
        assert len(result["risk_factors"]) > 0

    async def test_historical_analogues_present(
        self, svc: ExplainabilityDashboardService, session: AsyncSession,
    ):
        await _seed_basic_data(session)
        session.add(SimilarityAnalysis(
            symbol="TEST", query_start_date=date(2024, 1, 1), query_end_date=date(2024, 6, 1),
            window_days=60, lookback_days=365, min_similarity=70, total_matches=30,
            avg_similarity=75, avg_return_5d=2.5,
            avg_return_10d=5.0, avg_return_20d=8.0, avg_return_60d=12.0,
            max_matches=30, optimal_holding_period=10,
        ))
        await session.flush()
        result = await svc.get_dashboard("TEST", date(2024, 6, 5))
        assert len(result["historical_analogues"]) > 0


# ── Helpers ──

def _make_prediction(signal: str, confidence: float):
    return type("", (), {"overall_signal": signal, "overall_confidence": confidence})()


def _make_decision(rec: str, confidence: float):
    return type("", (), {"recommendation": rec, "confidence_score": confidence})()


def _make_ensemble(signal: str, confidence: float, agreement: str):
    return type("", (), {"ensemble_signal": signal, "ensemble_confidence": confidence, "agreement_level": agreement})()


def _make_stored(signal: str, confidence: float):
    return type("", (), {"overall_signal": signal, "overall_confidence": confidence})()


def _make_prediction_db(symbol: str, dt: date, signal: str, confidence: float) -> Prediction:
    return Prediction(
        symbol=symbol, as_of_date=dt, overall_signal=signal,
        overall_confidence=confidence, overall_score=75,
    )


def _make_decision_db(symbol: str, dt: date, rec: str, confidence: float) -> TradingDecision:
    return TradingDecision(
        symbol=symbol, as_of_date=dt, recommendation=rec,
        confidence_score=confidence, opportunity_score=70,
        metadata_json="{}",
    )


def _make_ensemble_db(symbol: str, dt: date, signal: str, confidence: float, agreement: str) -> EnsemblePrediction:
    return EnsemblePrediction(
        symbol=symbol, as_of_date=dt, ensemble_signal=signal,
        ensemble_confidence=confidence, agreement_level=agreement,
        ensemble_score=80, metadata_json="{}",
    )


async def _seed_basic_data(session: AsyncSession) -> None:
    session.add(Company(
        symbol="TEST", company_name="TestCorp", isin="US1234567890",
        exchange="NYSE", sector="Tech", status="active",
    ))
    session.add(DailyPrice(
        symbol="TEST", trade_date=date(2024, 6, 1),
        open=100, high=105, low=99, close=102, volume=1000000,
    ))
    session.add(TechnicalIndicator(
        symbol="TEST", trade_date=date(2024, 6, 1),
        indicator="rsi", params_hash="a", value=65,
    ))
    session.add(TechnicalIndicator(
        symbol="TEST", trade_date=date(2024, 6, 1),
        indicator="sma_20", params_hash="a", value=105,
    ))
    session.add(TechnicalIndicator(
        symbol="TEST", trade_date=date(2024, 6, 1),
        indicator="sma_50", params_hash="a", value=95,
    ))
    session.add(RiskMetrics(
        symbol="TEST", as_of_date=date(2024, 6, 1),
        composite_risk_score=25, volatility_252d=22,
        liquidity_score=80, max_drawdown_1y=10, event_risk_score=3,
    ))
    await session.flush()
