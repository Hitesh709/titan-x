from datetime import date, datetime, timedelta

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
from titan_x.models.prediction import Prediction
from titan_x.services.prediction_engine import PredictionEngine, HORIZONS


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
async def pe(session: AsyncSession) -> PredictionEngine:
    return PredictionEngine(session)


class TestReturnToSignal:
    @pytest.mark.asyncio
    async def test_strong_buy(self, pe: PredictionEngine) -> None:
        assert pe._return_to_signal(10, 80, 80) == "strong_buy"

    @pytest.mark.asyncio
    async def test_buy(self, pe: PredictionEngine) -> None:
        assert pe._return_to_signal(4, 60, 50) == "buy"

    @pytest.mark.asyncio
    async def test_hold(self, pe: PredictionEngine) -> None:
        assert pe._return_to_signal(0.5, 50, 50) == "hold"

    @pytest.mark.asyncio
    async def test_sell(self, pe: PredictionEngine) -> None:
        assert pe._return_to_signal(-4, 60, 50) == "sell"

    @pytest.mark.asyncio
    async def test_strong_sell(self, pe: PredictionEngine) -> None:
        assert pe._return_to_signal(-10, 80, 80) == "strong_sell"


class TestComputeHorizonPrediction:
    @pytest.mark.asyncio
    async def test_all_empty(self, pe: PredictionEngine) -> None:
        result = pe._compute_horizon_prediction(10, [], None, [], None, [], None, None, None)
        assert result["signal"] == "hold"
        assert result["probability"] == 50
        assert result["confidence"] == 20

    @pytest.mark.asyncio
    async def test_with_similarity_bullish(self, pe: PredictionEngine) -> None:
        class MockSA:
            avg_similarity = 75.0
            avg_return_5d = 5.0
            avg_return_10d = 8.0
            avg_return_20d = 12.0
            avg_return_60d = 18.0
            optimal_holding_period = 10

        result = pe._compute_horizon_prediction(
            10, [MockSA()], None, None, None, [], None, None, None,
        )
        assert result["expected_return"] > 0


class TestSimilarityReturn:
    @pytest.mark.asyncio
    async def test_direct_horizon_5d(self, pe: PredictionEngine) -> None:
        class MockSA:
            avg_return_5d = 3.5

        assert pe._get_similarity_return([MockSA()], 5) == 3.5

    @pytest.mark.asyncio
    async def test_direct_horizon_10d(self, pe: PredictionEngine) -> None:
        class MockSA:
            avg_return_10d = 7.0

        assert pe._get_similarity_return([MockSA()], 10) == 7.0

    @pytest.mark.asyncio
    async def test_interpolated_15d(self, pe: PredictionEngine) -> None:
        class MockSA:
            avg_return_10d = 5.0
            avg_return_20d = 10.0

        result = pe._get_similarity_return([MockSA()], 15)
        assert result is not None
        assert result == 7.5

    @pytest.mark.asyncio
    async def test_interpolated_30d(self, pe: PredictionEngine) -> None:
        class MockSA:
            avg_return_20d = 8.0
            avg_return_60d = 16.0

        result = pe._get_similarity_return([MockSA()], 30)
        assert result is not None
        assert result == 10.0

    @pytest.mark.asyncio
    async def test_no_similarity(self, pe: PredictionEngine) -> None:
        assert pe._get_similarity_return([], 10) is None


class TestTechnicalScore:
    @pytest.mark.asyncio
    async def test_no_technical(self, pe: PredictionEngine) -> None:
        assert pe._compute_technical_score(None, 10) is None

    @pytest.mark.asyncio
    async def test_bullish_sma(self, pe: PredictionEngine) -> None:
        class MockIndicator:
            value = 110.0
            value_secondary = None

        tech = {"sma_20": MockIndicator(), "sma_50": type("", (), {"value": 100.0})()}
        result = pe._compute_technical_score(tech, 10)
        assert result is not None
        assert result["return"] > 0

    @pytest.mark.asyncio
    async def test_bearish_rsi(self, pe: PredictionEngine) -> None:
        class MockIndicator:
            value = 75.0
            value_secondary = None

        tech = {"rsi": MockIndicator()}
        result = pe._compute_technical_score(tech, 10)
        assert result is not None
        assert result["return"] < 0


class TestPatternScore:
    @pytest.mark.asyncio
    async def test_bullish_pattern(self, pe: PredictionEngine) -> None:
        patterns = [
            type("", (), {"is_active": True, "confidence_score": 80.0, "direction": "bullish"})(),
        ]
        result = pe._compute_pattern_score(patterns, 20)
        assert result is not None
        assert result["return"] > 0

    @pytest.mark.asyncio
    async def test_bearish_pattern(self, pe: PredictionEngine) -> None:
        patterns = [
            type("", (), {"is_active": True, "confidence_score": 70.0, "direction": "bearish"})(),
        ]
        result = pe._compute_pattern_score(patterns, 20)
        assert result is not None
        assert result["return"] < 0

    @pytest.mark.asyncio
    async def test_inactive_pattern(self, pe: PredictionEngine) -> None:
        patterns = [
            type("", (), {"is_active": False, "confidence_score": 80.0, "direction": "bullish"})(),
        ]
        assert pe._compute_pattern_score(patterns, 20) is None

    @pytest.mark.asyncio
    async def test_low_confidence_pattern(self, pe: PredictionEngine) -> None:
        patterns = [
            type("", (), {"is_active": True, "confidence_score": 30.0, "direction": "bullish"})(),
        ]
        assert pe._compute_pattern_score(patterns, 20) is None

    @pytest.mark.asyncio
    async def test_no_patterns(self, pe: PredictionEngine) -> None:
        assert pe._compute_pattern_score([], 10) is None


class TestFundamentalScore:
    @pytest.mark.asyncio
    async def test_low_pe(self, pe: PredictionEngine) -> None:
        metrics = [
            type("", (), {"metric_name": "PE_RATIO", "value": 8.0})(),
        ]
        result = pe._compute_fundamental_score(metrics)
        assert result is not None
        assert result["return"] > 0

    @pytest.mark.asyncio
    async def test_high_pe(self, pe: PredictionEngine) -> None:
        metrics = [
            type("", (), {"metric_name": "PE_RATIO", "value": 60.0})(),
        ]
        result = pe._compute_fundamental_score(metrics)
        assert result is not None
        assert result["return"] < 0

    @pytest.mark.asyncio
    async def test_high_quality(self, pe: PredictionEngine) -> None:
        metrics = [
            type("", (), {"metric_name": "QUALITY_SCORE", "value": 85.0})(),
        ]
        result = pe._compute_fundamental_score(metrics)
        assert result is not None

    @pytest.mark.asyncio
    async def test_high_roe(self, pe: PredictionEngine) -> None:
        metrics = [
            type("", (), {"metric_name": "ROE", "value": 25.0})(),
        ]
        result = pe._compute_fundamental_score(metrics)
        assert result is not None
        assert result["return"] > 0

    @pytest.mark.asyncio
    async def test_no_fundamentals(self, pe: PredictionEngine) -> None:
        assert pe._compute_fundamental_score([]) is None


class TestSectorScore:
    @pytest.mark.asyncio
    async def test_positive_sector(self, pe: PredictionEngine) -> None:
        data = {"momentum_score": 10.0, "relative_strength": 60.0, "rotation_signal": "strengthening"}
        result = pe._compute_sector_score(data, 20)
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_sector(self, pe: PredictionEngine) -> None:
        assert pe._compute_sector_score(None, 10) is None


class TestBreadthScore:
    @pytest.mark.asyncio
    async def test_strong_breadth(self, pe: PredictionEngine) -> None:
        data = {"index_strength_score": 80.0, "adv_decl_ratio": 2.0}
        result = pe._compute_breadth_score(data, 20)
        assert result is not None
        assert result["return"] > 0

    @pytest.mark.asyncio
    async def test_weak_breadth(self, pe: PredictionEngine) -> None:
        data = {"index_strength_score": 20.0, "adv_decl_ratio": 0.3}
        result = pe._compute_breadth_score(data, 20)
        assert result is not None
        assert result["return"] < 0

    @pytest.mark.asyncio
    async def test_no_breadth(self, pe: PredictionEngine) -> None:
        assert pe._compute_breadth_score(None, 10) is None


class TestExpectedDrawdown:
    @pytest.mark.asyncio
    async def test_default_vol(self, pe: PredictionEngine) -> None:
        dd = pe._compute_expected_drawdown(10, None, 0)
        assert 0 < dd < 50

    @pytest.mark.asyncio
    async def test_with_risk_metrics(self, pe: PredictionEngine) -> None:
        risk = type("", (), {"volatility_252d": 25.0, "max_drawdown_1y": 15.0, "event_risk_score": 5.0})()
        dd = pe._compute_expected_drawdown(20, risk, 2)
        assert 0 < dd < 50

    @pytest.mark.asyncio
    async def test_negative_return_increases_dd(self, pe: PredictionEngine) -> None:
        risk = type("", (), {"volatility_252d": 20.0, "max_drawdown_1y": 10.0, "event_risk_score": 3.0})()
        dd_positive = pe._compute_expected_drawdown(10, risk, 5)
        dd_negative = pe._compute_expected_drawdown(10, risk, -5)
        assert dd_negative >= dd_positive


class TestProbability:
    @pytest.mark.asyncio
    async def test_bullish_probability(self, pe: PredictionEngine) -> None:
        prob = pe._compute_probability(5, 0.8, [{"value": 3, "weight": 1, "conf": 0.8}])
        assert 50 < prob <= 95

    @pytest.mark.asyncio
    async def test_bearish_probability(self, pe: PredictionEngine) -> None:
        prob = pe._compute_probability(-5, 0.8, [{"value": -3, "weight": 1, "conf": 0.8}])
        assert prob == 51.0  # base=30, agreement=100 => 30*0.7 + 100*0.3 = 51

    @pytest.mark.asyncio
    async def test_neutral_probability(self, pe: PredictionEngine) -> None:
        prob = pe._compute_probability(0, 0.5, [])
        assert prob == 50


class TestSignalAgreement:
    @pytest.mark.asyncio
    async def test_all_positive(self, pe: PredictionEngine) -> None:
        agreement = pe._compute_signal_agreement([{"value": 2}, {"value": 3}])
        assert agreement == 100

    @pytest.mark.asyncio
    async def test_mixed(self, pe: PredictionEngine) -> None:
        agreement = pe._compute_signal_agreement([{"value": 2}, {"value": -3}])
        assert agreement == 50

    @pytest.mark.asyncio
    async def test_all_neutral(self, pe: PredictionEngine) -> None:
        agreement = pe._compute_signal_agreement([{"value": 0}, {"value": 0}])
        assert agreement == 50

    @pytest.mark.asyncio
    async def test_empty(self, pe: PredictionEngine) -> None:
        agreement = pe._compute_signal_agreement([])
        assert agreement == 50


class TestComputeOverall:
    @pytest.mark.asyncio
    async def test_all_bullish(self, pe: PredictionEngine) -> None:
        hd = {h: {"expected_return": 5, "confidence": 70, "probability": 70} for h in HORIZONS}
        score, signal, conf = pe._compute_overall(hd)
        assert signal in ("buy", "strong_buy")

    @pytest.mark.asyncio
    async def test_all_bearish(self, pe: PredictionEngine) -> None:
        hd = {h: {"expected_return": -5, "confidence": 70, "probability": 70} for h in HORIZONS}
        score, signal, conf = pe._compute_overall(hd)
        assert signal in ("sell", "strong_sell")

    @pytest.mark.asyncio
    async def test_neutral(self, pe: PredictionEngine) -> None:
        hd = {h: {"expected_return": 0, "confidence": 50, "probability": 50} for h in HORIZONS}
        score, signal, conf = pe._compute_overall(hd)
        assert signal == "hold"


class TestFullPrediction:
    @pytest.mark.asyncio
    async def test_company_not_found(self, pe: PredictionEngine) -> None:
        result = await pe.predict("NONEXIST")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_predict_with_data(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="rsi", params_hash="a", value=65))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="sma_20", params_hash="a", value=100))
        session.add(TechnicalIndicator(symbol="TEST", trade_date=date(2024, 6, 1), indicator="sma_50", params_hash="a", value=95))
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=25, volatility_252d=22, liquidity_score=80))

        sa = SimilarityAnalysis(
            symbol="TEST", query_start_date=date(2024, 1, 1), query_end_date=date(2024, 6, 1),
            window_days=20, lookback_days=365, max_matches=50, min_similarity=60,
            avg_return_5d=2.0, avg_return_10d=4.0, avg_return_20d=6.0, avg_return_60d=10.0,
            avg_similarity=70.0, optimal_holding_period=10,
        )
        session.add(sa)
        await session.flush()

        result = await pe.predict("TEST", date(2024, 6, 5), store=False)
        assert "error" not in result
        assert result["overall_signal"] is not None
        for h in [5, 10, 15, 20, 30]:
            assert result.get(f"probability_{h}d") is not None
            assert result.get(f"expected_return_{h}d") is not None
            assert result.get(f"expected_drawdown_{h}d") is not None
            assert result.get(f"confidence_{h}d") is not None
            assert result.get(f"signal_{h}d") is not None
        assert result["holding_period"] is not None
        assert result["explanation"] is not None

    @pytest.mark.asyncio
    async def test_predict_and_store(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        result = await pe.predict("TEST", date(2024, 6, 5), store=True)
        assert result.get("id") is not None

        pred = await pe.get_prediction("TEST")
        assert pred is not None
        assert pred.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_duplicate_store(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        await pe.predict("TEST", date(2024, 6, 5), store=True)
        with pytest.raises(ValueError, match="already exists"):
            await pe.predict("TEST", date(2024, 6, 5), store=True)

    @pytest.mark.asyncio
    async def test_prediction_history(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        await pe.predict("TEST", date(2024, 6, 1), store=True)
        rows, total = await pe.get_prediction_history(symbol="TEST")
        assert total >= 1

    @pytest.mark.asyncio
    async def test_delete_prediction(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        session.add(DailyPrice(symbol="TEST", trade_date=date(2024, 6, 1), open=100, high=105, low=99, close=102, volume=1000000))
        await session.flush()

        result = await pe.predict("TEST", date(2024, 6, 1), store=True)
        assert await pe.delete_prediction(result["id"]) is True
        assert await pe.delete_prediction(result["id"]) is False


class TestDataFetching:
    @pytest.mark.asyncio
    async def test_get_company_found(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(Company(symbol="TEST", company_name="TestCorp", isin="US1234567890", exchange="NYSE", sector="Tech", status="active"))
        await session.flush()
        company = await pe._get_company("TEST")
        assert company is not None
        assert company.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_get_company_not_found(self, pe: PredictionEngine) -> None:
        assert await pe._get_company("NONEXIST") is None

    @pytest.mark.asyncio
    async def test_get_risk_no_data(self, pe: PredictionEngine) -> None:
        risk = await pe._get_risk_metrics("TEST", date.today())
        assert risk is None

    @pytest.mark.asyncio
    async def test_get_risk_with_data(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(RiskMetrics(symbol="TEST", as_of_date=date(2024, 6, 1), composite_risk_score=25, volatility_252d=22))
        await session.flush()
        risk = await pe._get_risk_metrics("TEST", date(2024, 6, 5))
        assert risk is not None
        assert risk.composite_risk_score == 25

    @pytest.mark.asyncio
    async def test_sector_no_sector(self, pe: PredictionEngine) -> None:
        assert await pe._get_sector_data(None, date.today()) is None

    @pytest.mark.asyncio
    async def test_sector_with_data(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(SectorPerformance(sector="Tech", as_of_date=date(2024, 6, 1), period_label="1M", momentum_score=10, relative_strength=55))
        await session.flush()
        data = await pe._get_sector_data("Tech", date(2024, 6, 5))
        assert data is not None
        assert "momentum_score" in data
        assert data["rotation_signal"] == "neutral"

    @pytest.mark.asyncio
    async def test_breadth_no_data(self, pe: PredictionEngine) -> None:
        assert await pe._get_market_breadth(date.today()) is None

    @pytest.mark.asyncio
    async def test_breadth_with_data(self, pe: PredictionEngine, session: AsyncSession) -> None:
        session.add(MarketBreadth(trade_date=date(2024, 6, 1), advancing=300, declining=200, unchanged=50, total_stocks=550, advancing_volume=100000, declining_volume=80000, unchanged_volume=5000, total_volume=185000, new_highs=30, new_lows=10, index_strength_score=65))
        await session.flush()
        data = await pe._get_market_breadth(date(2024, 6, 5))
        assert data is not None

    @pytest.mark.asyncio
    async def test_technical_no_data(self, pe: PredictionEngine) -> None:
        data = await pe._get_technical_data("TEST", date.today())
        assert data == {}
