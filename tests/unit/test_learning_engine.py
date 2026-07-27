import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.learning import LearningHistory, ModelWeight
from titan_x.models.prediction import Prediction
from titan_x.models.price import DailyPrice
from titan_x.models.user import User
from titan_x.services.learning_engine import (
    HORIZONS,
    LearningEngine,
    SOURCE_NAMES,
    SIGNAL_DIRECTION,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        await sess.execute(select(1).where(True))
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    u = User(email="learn@test.com", hashed_password="h")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
async def price_data(session: AsyncSession) -> None:
    today = date.today()
    for i in range(60):
        close = 100.0 + i * 0.5
        dp = DailyPrice(
            symbol="LEARN",
            trade_date=today - timedelta(days=59 - i),
            open=close - 0.2, high=close + 0.5, low=close - 0.5,
            close=close, volume=1_000_000,
        )
        session.add(dp)
    await session.flush()


@pytest_asyncio.fixture
async def prediction(session: AsyncSession, user: User) -> Prediction:
    pred = Prediction(
        symbol="LEARN",
        as_of_date=date.today() - timedelta(days=40),
        signal_5d="buy",
        expected_return_5d=3.0,
        confidence_5d=70.0,
        probability_5d=60.0,
        signal_10d="strong_buy",
        expected_return_10d=6.0,
        confidence_10d=80.0,
        probability_10d=70.0,
        signal_15d="buy",
        expected_return_15d=4.0,
        confidence_15d=65.0,
        probability_15d=55.0,
        signal_20d="hold",
        expected_return_20d=1.0,
        confidence_20d=50.0,
        probability_20d=50.0,
        signal_30d="sell",
        expected_return_30d=-3.0,
        confidence_30d=60.0,
        probability_30d=55.0,
        overall_signal="buy",
        overall_confidence=65.0,
        data_sources_json=json.dumps({
            "has_technical": True, "has_patterns": False,
            "has_fundamentals": True, "has_similarity": False,
        }),
    )
    session.add(pred)
    await session.flush()
    return pred


# ============================================================
# EVALUATE PREDICTION
# ============================================================

class TestEvaluatePrediction:
    @pytest.mark.asyncio
    async def test_evaluate_single_prediction(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        result = await engine.evaluate_prediction(prediction.id)
        assert result["prediction_id"] == prediction.id
        assert result["symbol"] == "LEARN"
        assert len(result["results"]) > 0

        for r in result["results"]:
            assert "horizon" in r
            assert "was_correct" in r
            assert r["actual_return"] is not None

    @pytest.mark.asyncio
    async def test_evaluate_nonexistent(self, session: AsyncSession):
        engine = LearningEngine(session)
        with pytest.raises(ValueError, match="Prediction 9999 not found"):
            await engine.evaluate_prediction(9999)

    @pytest.mark.asyncio
    async def test_evaluate_no_price_data(self, session: AsyncSession, user: User):
        pred = Prediction(
            symbol="NODATA", as_of_date=date.today() - timedelta(days=40),
            signal_5d="buy", expected_return_5d=3.0,
        )
        session.add(pred)
        await session.flush()
        engine = LearningEngine(session)
        result = await engine.evaluate_prediction(pred.id)
        assert len(result["results"]) == 0

    @pytest.mark.asyncio
    async def test_evaluate_creates_history(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        rows = (await session.execute(
            select(LearningHistory).where(LearningHistory.prediction_id == prediction.id)
        )).scalars().all()
        assert len(rows) > 0
        for r in rows:
            assert r.predicted_signal is not None
            assert r.actual_return_pct is not None
            assert r.was_correct is not None

    @pytest.mark.asyncio
    async def test_evaluate_correct_direction(self, session: AsyncSession, user: User, price_data):
        today = date.today()
        start = today - timedelta(days=30)
        pred = Prediction(
            symbol="LEARN", as_of_date=start,
            signal_10d="buy", expected_return_10d=5.0,
        )
        session.add(pred)
        await session.flush()
        engine = LearningEngine(session)
        result = await engine.evaluate_prediction(pred.id)
        r = next((x for x in result["results"] if x["horizon"] == 10), None)
        assert r is not None
        assert r["actual_return"] > 0


# ============================================================
# EVALUATE OUTDATED
# ============================================================

class TestEvaluateOutdated:
    @pytest.mark.asyncio
    async def test_evaluate_outdated_finds_predictions(self, session: AsyncSession, user: User, price_data, prediction):
        today = date.today()
        engine = LearningEngine(session)
        results = await engine.evaluate_outdated_predictions(max_records=50)
        assert len(results) >= 1
        ids = [r["prediction_id"] for r in results]
        assert prediction.id in ids

    @pytest.mark.asyncio
    async def test_evaluate_outdated_skips_recent(self, session: AsyncSession, user: User, price_data):
        pred = Prediction(
            symbol="LEARN", as_of_date=date.today(),
            signal_5d="buy", expected_return_5d=2.0,
        )
        session.add(pred)
        await session.flush()
        engine = LearningEngine(session)
        results = await engine.evaluate_outdated_predictions()
        ids = [r["prediction_id"] for r in results]
        assert pred.id not in ids

    @pytest.mark.asyncio
    async def test_evaluate_outdated_skips_already_evaluated(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        results = await engine.evaluate_outdated_predictions()
        ids = [r["prediction_id"] for r in results]
        assert prediction.id not in ids


# ============================================================
# COMPUTE SUMMARY
# ============================================================

class TestComputeSummary:
    @pytest.mark.asyncio
    async def test_summary_with_data(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        summary = await engine.compute_summary(symbol="LEARN")
        assert summary["total"] > 0
        assert summary["accuracy"] >= 0
        assert summary["profitability"] is not None

    @pytest.mark.asyncio
    async def test_summary_empty(self, session: AsyncSession):
        engine = LearningEngine(session)
        summary = await engine.compute_summary()
        assert summary["total"] == 0

    @pytest.mark.asyncio
    async def test_summary_by_horizon(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        summary = await engine.compute_summary(symbol="LEARN", horizon_days=5)
        assert summary["total"] >= 0


# ============================================================
# UPDATE WEIGHTS
# ============================================================

class TestUpdateSourceWeights:
    @pytest.mark.asyncio
    async def test_update_technical_weight(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        result = await engine.update_source_weights("technical")
        assert result["source"] == "technical"
        assert result["total"] >= 0
        assert "new_weight" in result

    @pytest.mark.asyncio
    async def test_update_nonexistent_source(self, session: AsyncSession):
        engine = LearningEngine(session)
        result = await engine.update_source_weights("unknown_source")
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_update_all_weights(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        results = await engine.update_all_weights()
        for source in SOURCE_NAMES:
            assert source in results
        assert "normalized_weights" in results
        nw = results["normalized_weights"]
        total = sum(nw.values())
        assert abs(total - 1.0) < 0.01


class TestNormalizeWeights:
    @pytest.mark.asyncio
    async def test_normalize_empty(self, session: AsyncSession):
        engine = LearningEngine(session)
        weights = await engine.normalize_weights()
        assert weights == {
            "technical": 0.20, "fundamental": 0.20, "news": 0.15,
            "macro": 0.15, "risk": 0.15, "pattern": 0.15,
        }

    @pytest.mark.asyncio
    async def test_normalize_with_data(self, session: AsyncSession):
        session.add(ModelWeight(source_name="technical", weight=0.3, total_predictions=0, correct_predictions=0))
        session.add(ModelWeight(source_name="fundamental", weight=0.5, total_predictions=0, correct_predictions=0))
        await session.flush()

        engine = LearningEngine(session)
        weights = await engine.normalize_weights()
        assert abs(weights["technical"] - 0.375) < 0.01
        assert abs(weights["fundamental"] - 0.625) < 0.01


# ============================================================
# GET WEIGHTS
# ============================================================

class TestGetWeights:
    @pytest.mark.asyncio
    async def test_get_all_weights(self, session: AsyncSession):
        session.add(ModelWeight(source_name="technical", weight=0.25, total_predictions=10, correct_predictions=7))
        session.add(ModelWeight(source_name="fundamental", weight=0.20, total_predictions=10, correct_predictions=6))
        await session.flush()

        engine = LearningEngine(session)
        weights = await engine.get_weights()
        assert len(weights) == 2
        names = [w["source_name"] for w in weights]
        assert "technical" in names
        assert "fundamental" in names

    @pytest.mark.asyncio
    async def test_get_filtered(self, session: AsyncSession):
        session.add(ModelWeight(source_name="technical", weight=0.25, total_predictions=10, correct_predictions=7))
        session.add(ModelWeight(source_name="fundamental", weight=0.20, total_predictions=10, correct_predictions=6))
        await session.flush()

        engine = LearningEngine(session)
        weights = await engine.get_weights(source_name="technical")
        assert len(weights) == 1
        assert weights[0]["source_name"] == "technical"
        assert weights[0]["total_predictions"] == 10


# ============================================================
# LEARNING HISTORY CRUD
# ============================================================

class TestLearningHistory:
    @pytest.mark.asyncio
    async def test_get_history(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        rows, total = await engine.get_history(symbol="LEARN")
        assert total > 0
        assert rows[0].symbol == "LEARN"

    @pytest.mark.asyncio
    async def test_get_history_filtered_by_correct(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        rows, total = await engine.get_history(was_correct=True)
        correct_count = total
        rows, total = await engine.get_history(was_correct=False)
        assert total + correct_count >= 0

    @pytest.mark.asyncio
    async def test_get_history_empty(self, session: AsyncSession):
        engine = LearningEngine(session)
        rows, total = await engine.get_history()
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_history_record(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        rows, _ = await engine.get_history(limit=1)
        record = await engine.get_history_record(rows[0].id)
        assert record is not None
        assert record["symbol"] == "LEARN"
        assert record["was_correct"] is not None

    @pytest.mark.asyncio
    async def test_get_history_record_not_found(self, session: AsyncSession):
        engine = LearningEngine(session)
        record = await engine.get_history_record(9999)
        assert record is None

    @pytest.mark.asyncio
    async def test_delete_history(self, session: AsyncSession, user: User, price_data, prediction):
        engine = LearningEngine(session)
        await engine.evaluate_prediction(prediction.id)
        rows, _ = await engine.get_history(limit=1)
        deleted = await engine.delete_history(rows[0].id)
        assert deleted is True
        record = await engine.get_history_record(rows[0].id)
        assert record is None

    @pytest.mark.asyncio
    async def test_delete_history_not_found(self, session: AsyncSession):
        engine = LearningEngine(session)
        deleted = await engine.delete_history(9999)
        assert deleted is False


# ============================================================
# EDGE CASES
# ============================================================

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_signal_direction_mapping(self):
        assert SIGNAL_DIRECTION["strong_buy"] == 1
        assert SIGNAL_DIRECTION["buy"] == 1
        assert SIGNAL_DIRECTION["bullish"] == 1
        assert SIGNAL_DIRECTION["hold"] == 0
        assert SIGNAL_DIRECTION["neutral"] == 0
        assert SIGNAL_DIRECTION["sell"] == -1
        assert SIGNAL_DIRECTION["bearish"] == -1
        assert SIGNAL_DIRECTION["strong_sell"] == -1

    @pytest.mark.asyncio
    async def test_default_horizons(self):
        assert HORIZONS == [5, 10, 15, 20, 30]

    @pytest.mark.asyncio
    async def test_source_names(self):
        assert "technical" in SOURCE_NAMES
        assert "fundamental" in SOURCE_NAMES
        assert "pattern" in SOURCE_NAMES

    @pytest.mark.asyncio
    async def test_return_to_signal(self):
        engine = LearningEngine.__new__(LearningEngine)
        assert engine._return_to_signal(3.0) == "bullish"
        assert engine._return_to_signal(-3.0) == "bearish"
        assert engine._return_to_signal(0.5) == "neutral"
        assert engine._return_to_signal(2.1) == "bullish"
        assert engine._return_to_signal(-2.1) == "bearish"

    @pytest.mark.asyncio
    async def test_profitability_no_trades(self, session: AsyncSession):
        engine = LearningEngine(session)
        summary = await engine.compute_summary()
        assert summary["profitability"] == 0
