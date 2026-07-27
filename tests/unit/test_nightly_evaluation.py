import json
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.nightly_evaluation import NightlyEvaluation, PredictionError
from titan_x.models.prediction import Prediction
from titan_x.models.price import DailyPrice
from titan_x.services.nightly_evaluation_service import NightlyEvaluationService

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
    return NightlyEvaluationService(session)


def _seed_prediction(session, symbol, as_of_date, signal_5d, expected_return_5d,
                     confidence_5d=0.8):
    p = Prediction(
        symbol=symbol, as_of_date=as_of_date,
        signal_5d=signal_5d, expected_return_5d=expected_return_5d,
        probability_5d=0.6, confidence_5d=confidence_5d,
        overall_signal=signal_5d,
    )
    session.add(p)
    return p


def _seed_price(session, symbol, trade_date, close):
    dp = DailyPrice(
        symbol=symbol, trade_date=trade_date,
        open=close, high=close * 1.02, low=close * 0.98,
        close=close, volume=1_000_000,
    )
    session.add(dp)
    return dp


class TestRunEvaluation:
    async def test_no_predictions(self, service, session):
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.total_predictions == 0
        assert ev.status == "completed"

    async def test_correct_bullish_prediction(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 10.0, confidence_5d=0.8)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.total_predictions == 1
        assert ev.correct_predictions == 1
        assert ev.accuracy == 100.0

    async def test_incorrect_bullish_prediction(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 95.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 5.0, confidence_5d=0.7)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.total_predictions == 1
        assert ev.correct_predictions == 0
        assert ev.accuracy == 0.0

    async def test_bearish_correct(self, service, session):
        _seed_price(session, "MSFT", date(2025, 6, 1), 200.0)
        _seed_price(session, "MSFT", date(2025, 6, 6), 180.0)
        _seed_prediction(session, "MSFT", date(2025, 6, 1),
                         "bearish", -10.0, confidence_5d=0.8)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.total_predictions == 1
        assert ev.correct_predictions == 1

    async def test_mixed_predictions(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 110.0)
        _seed_price(session, "MSFT", date(2025, 6, 1), 200.0)
        _seed_price(session, "MSFT", date(2025, 6, 6), 195.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 10.0, confidence_5d=0.8)
        _seed_prediction(session, "MSFT", date(2025, 6, 1),
                         "bullish", 5.0, confidence_5d=0.7)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.total_predictions == 2
        assert ev.accuracy == 50.0

    async def test_mae_and_rmse_computed(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 105.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 10.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.mae is not None
        assert ev.mae > 0
        assert ev.rmse is not None

    async def test_bias_detected(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 100.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 15.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.bias_score is not None
        assert ev.bias_direction == "overprediction"

    async def test_underprediction_bias(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 100.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bearish", -15.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.bias_score is not None
        assert ev.bias_direction == "underprediction"

    async def test_failures_detected(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 100.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 20.0)
        await session.flush()
        ev = await service.run_evaluation(
            evaluation_date=date(2025, 6, 15), lookback_days=30,
            failure_threshold_pct=5.0,
        )
        assert ev.failure_count == 1

    async def test_stores_prediction_errors(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 10.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        errors = await service.get_errors(ev.id)
        assert len(errors) == 1
        assert errors[0].symbol == "AAPL"
        assert errors[0].was_correct is True

    async def test_no_price_data_skips(self, service, session):
        _seed_prediction(session, "NODATA", date(2025, 6, 1),
                         "bullish", 10.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.total_predictions == 0

    async def test_weight_adjustment_json_present(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 10.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.weight_adjustments_json is not None
        adj = json.loads(ev.weight_adjustments_json)
        assert "recommendation_summary" in adj

    async def test_summary_json_present(self, service, session):
        _seed_price(session, "AAPL", date(2025, 6, 1), 100.0)
        _seed_price(session, "AAPL", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "AAPL", date(2025, 6, 1),
                         "bullish", 10.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15), lookback_days=30)
        assert ev.summary_json is not None
        summary = json.loads(ev.summary_json)
        assert "period" in summary
        assert "accuracy" in summary


class TestQuery:
    async def test_get_evaluation(self, service, session):
        _seed_price(session, "X", date(2025, 6, 1), 100.0)
        _seed_price(session, "X", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "X", date(2025, 6, 1), "bullish", 10.0)
        await session.flush()
        ev = await service.run_evaluation(evaluation_date=date(2025, 6, 15))
        found = await service.get_evaluation(ev.id)
        assert found is not None
        assert found.id == ev.id

    async def test_get_evaluation_not_found(self, service):
        found = await service.get_evaluation(9999)
        assert found is None

    async def test_list_evaluations(self, service, session):
        _seed_price(session, "X", date(2025, 6, 1), 100.0)
        _seed_price(session, "X", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "X", date(2025, 6, 1), "bullish", 10.0)
        await session.flush()
        await service.run_evaluation(evaluation_date=date(2025, 6, 15))
        await service.run_evaluation(evaluation_date=date(2025, 6, 16), lookback_days=5)
        evals = await service.get_evaluations()
        assert len(evals) >= 2

    async def test_get_errors_filters_failures(self, service, session):
        _seed_price(session, "A", date(2025, 6, 1), 100.0)
        _seed_price(session, "A", date(2025, 6, 6), 100.0)
        _seed_price(session, "B", date(2025, 6, 1), 200.0)
        _seed_price(session, "B", date(2025, 6, 6), 210.0)
        _seed_prediction(session, "A", date(2025, 6, 1), "bullish", 20.0)
        _seed_prediction(session, "B", date(2025, 6, 1), "bullish", 5.0)
        await session.flush()
        ev = await service.run_evaluation(
            evaluation_date=date(2025, 6, 15),
            failure_threshold_pct=10.0,
        )
        failures = await service.get_failures(ev.id)
        assert len(failures) == 1
        assert failures[0].symbol == "A"

    async def test_latest_evaluation(self, service, session):
        _seed_price(session, "X", date(2025, 6, 1), 100.0)
        _seed_price(session, "X", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "X", date(2025, 6, 1), "bullish", 10.0)
        await session.flush()
        await service.run_evaluation(evaluation_date=date(2025, 6, 15))
        latest = await service.get_latest_evaluation()
        assert latest is not None

    async def test_trend(self, service, session):
        _seed_price(session, "X", date(2025, 6, 1), 100.0)
        _seed_price(session, "X", date(2025, 6, 6), 110.0)
        _seed_prediction(session, "X", date(2025, 6, 1), "bullish", 10.0)
        await session.flush()
        await service.run_evaluation(evaluation_date=date(2025, 6, 15))
        trend = await service.get_trend()
        assert len(trend) >= 1
        assert all("accuracy" in t for t in trend)


