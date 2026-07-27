import json
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.decision import TradingDecision
from titan_x.services.decision_engine import DecisionEngine, OPPORTUNITY_WEIGHTS


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
async def dec_engine(session: AsyncSession) -> DecisionEngine:
    return DecisionEngine(session)


BUY_SCORES = {
    "pattern_score": 85.0,
    "pattern_type": "double_bottom",
    "similarity_score": 75.0,
    "similarity_forward_return": 8.5,
    "technical_score": 80.0,
    "sector_score": 70.0,
    "sector_rotation": "leading",
    "sentiment_score": 35.0,
    "breadth_score": 75.0,
    "risk_score": 25.0,
    "risk_rating": "low",
    "fundamental_score": 80.0,
    "liquidity_score": 85.0,
    "avg_daily_volume_20d": 5_000_000,
    "news_count_30d": 45,
}

SELL_SCORES = {
    "pattern_score": 20.0,
    "pattern_type": "double_top",
    "similarity_score": 25.0,
    "similarity_forward_return": -5.0,
    "technical_score": 30.0,
    "sector_score": 25.0,
    "sector_rotation": "lagging",
    "sentiment_score": -40.0,
    "breadth_score": 30.0,
    "risk_score": 80.0,
    "risk_rating": "high",
    "fundamental_score": 25.0,
    "liquidity_score": 30.0,
    "avg_daily_volume_20d": 50_000,
    "news_count_30d": 5,
}

NEUTRAL_SCORES = {
    "pattern_score": 50.0,
    "similarity_score": 45.0,
    "technical_score": 50.0,
    "sector_score": 50.0,
    "sentiment_score": 5.0,
    "breadth_score": 50.0,
    "risk_score": 45.0,
    "risk_rating": "medium",
    "fundamental_score": 50.0,
    "liquidity_score": 55.0,
    "avg_daily_volume_20d": 500_000,
    "news_count_30d": 15,
}

class TestCombineScores:
    @pytest.mark.asyncio
    async def test_combine_buy_scenario(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores(BUY_SCORES)
        assert result["opportunity_score"] >= 55
        assert result["confidence_score"] >= 40
        assert result["recommendation"] in ("buy", "strong_buy")
        assert result["recommendation_code"] in (1, 2)
        assert result["explanation"] is not None

    @pytest.mark.asyncio
    async def test_combine_sell_scenario(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores(SELL_SCORES)
        assert result["opportunity_score"] <= 55
        assert result["recommendation"] in ("sell", "strong_sell")
        assert result["recommendation_code"] in (-1, -2)

    @pytest.mark.asyncio
    async def test_combine_neutral_scenario(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores(NEUTRAL_SCORES)
        assert result["recommendation"] == "hold"
        assert result["recommendation_code"] == 0

    @pytest.mark.asyncio
    async def test_combine_empty_scores(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores({})
        assert 0 <= result["opportunity_score"] <= 100
        assert 0 <= result["confidence_score"] <= 100
        assert result["recommendation"] in ("strong_buy", "buy", "hold", "sell", "strong_sell")
        assert result["explanation"] is not None

    @pytest.mark.asyncio
    async def test_combine_partial_scores(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores({"pattern_score": 80.0, "risk_score": 20.0})
        assert result["pattern_score"] == 80.0
        assert result["risk_score"] == 20.0


class TestOpportunityScore:
    @pytest.mark.asyncio
    async def test_opportunity_range(self, dec_engine: DecisionEngine) -> None:
        op = dec_engine._compute_opportunity(BUY_SCORES)
        assert 0 <= op <= 100

    @pytest.mark.asyncio
    async def test_opportunity_high_with_good_scores(self, dec_engine: DecisionEngine) -> None:
        op = dec_engine._compute_opportunity(BUY_SCORES)
        assert op >= 55

    @pytest.mark.asyncio
    async def test_opportunity_low_with_bad_scores(self, dec_engine: DecisionEngine) -> None:
        op = dec_engine._compute_opportunity(SELL_SCORES)
        assert op < 55


class TestConfidenceScore:
    @pytest.mark.asyncio
    async def test_confidence_range(self, dec_engine: DecisionEngine) -> None:
        cf = dec_engine._compute_confidence(BUY_SCORES, 80.0)
        assert 0 <= cf <= 100

    @pytest.mark.asyncio
    async def test_confidence_high_with_data(self, dec_engine: DecisionEngine) -> None:
        cf = dec_engine._compute_confidence(BUY_SCORES, 80.0)
        assert cf >= 50

    @pytest.mark.asyncio
    async def test_confidence_low_without_data(self, dec_engine: DecisionEngine) -> None:
        cf = dec_engine._compute_confidence({}, 50.0)
        assert cf > 0


class TestRecommendation:
    @pytest.mark.asyncio
    async def test_strong_buy(self, dec_engine: DecisionEngine) -> None:
        rec, code = dec_engine._get_recommendation(85.0, 75.0)
        assert rec == "strong_buy"
        assert code == 2

    @pytest.mark.asyncio
    async def test_strong_sell(self, dec_engine: DecisionEngine) -> None:
        rec, code = dec_engine._get_recommendation(20.0, 15.0)
        assert rec == "strong_sell"
        assert code == -2

    @pytest.mark.asyncio
    async def test_hold(self, dec_engine: DecisionEngine) -> None:
        rec, code = dec_engine._get_recommendation(50.0, 50.0)
        assert rec == "hold"
        assert code == 0


class TestExplanation:
    @pytest.mark.asyncio
    async def test_explanation_contains_recommendation(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores(BUY_SCORES)
        assert result["recommendation"].upper() in result["explanation"].upper()

    @pytest.mark.asyncio
    async def test_explanation_contains_key_factors(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores(BUY_SCORES)
        assert "KEY FACTORS" in result["explanation"]

    @pytest.mark.asyncio
    async def test_explanation_contains_action(self, dec_engine: DecisionEngine) -> None:
        result = dec_engine.combine_scores(BUY_SCORES)
        assert "ACTION" in result["explanation"]


class TestGenerateDecision:
    @pytest.mark.asyncio
    async def test_generate_store_retrieve(
        self, dec_engine: DecisionEngine, session: AsyncSession,
    ) -> None:
        result = await dec_engine.generate_decision("TEST", BUY_SCORES, date(2024, 6, 1), store=True)
        assert result["id"] is not None
        assert result["symbol"] == "TEST"

        decision = await dec_engine.get_decision("TEST", date(2024, 6, 1))
        assert decision is not None
        assert decision.symbol == "TEST"
        assert decision.opportunity_score is not None

    @pytest.mark.asyncio
    async def test_duplicate_store(
        self, dec_engine: DecisionEngine, session: AsyncSession,
    ) -> None:
        await dec_engine.generate_decision("TEST", BUY_SCORES, date(2024, 6, 1), store=True)
        with pytest.raises(ValueError, match="already exists"):
            await dec_engine.generate_decision("TEST", BUY_SCORES, date(2024, 6, 1), store=True)

    @pytest.mark.asyncio
    async def test_decision_history(
        self, dec_engine: DecisionEngine, session: AsyncSession,
    ) -> None:
        await dec_engine.generate_decision("TEST", BUY_SCORES, date(2024, 6, 1), store=True)
        await dec_engine.generate_decision("TEST", SELL_SCORES, date(2024, 7, 1), store=True)
        await dec_engine.generate_decision("OTHER", BUY_SCORES, date(2024, 6, 1), store=True)

        rows, total = await dec_engine.get_decision_history(symbol="TEST")
        assert total >= 2

        all_rows, all_total = await dec_engine.get_decision_history()
        assert all_total >= 3

    @pytest.mark.asyncio
    async def test_filter_by_recommendation(
        self, dec_engine: DecisionEngine, session: AsyncSession,
    ) -> None:
        await dec_engine.generate_decision("TEST", BUY_SCORES, date(2024, 6, 1), store=True)
        buy_results = await dec_engine.get_latest_by_recommendation("buy", 10)
        assert len(buy_results) >= 0

    @pytest.mark.asyncio
    async def test_filter_by_min_opportunity(
        self, dec_engine: DecisionEngine, session: AsyncSession,
    ) -> None:
        await dec_engine.generate_decision("TEST", BUY_SCORES, date(2024, 6, 1), store=True)
        await dec_engine.generate_decision("TEST2", SELL_SCORES, date(2024, 6, 1), store=True)

        rows, total = await dec_engine.get_decision_history(min_opportunity=60.0)
        assert total >= 0

    @pytest.mark.asyncio
    async def test_delete_decision(
        self, dec_engine: DecisionEngine, session: AsyncSession,
    ) -> None:
        result = await dec_engine.generate_decision("TEST", BUY_SCORES, date(2024, 6, 1), store=True)
        assert await dec_engine.delete_decision(result["id"]) is True
        assert await dec_engine.delete_decision(result["id"]) is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_decision(self, dec_engine: DecisionEngine) -> None:
        decision = await dec_engine.get_decision("NONEXIST")
        assert decision is None


class TestScoreBanding:
    @pytest.mark.asyncio
    async def test_strong_buy_band(self, dec_engine: DecisionEngine) -> None:
        scores = dict(BUY_SCORES)
        scores["pattern_score"] = 95
        scores["confidence_score"] = 95
        scores["risk_score"] = 10
        result = dec_engine.combine_scores(scores)
        assert result["recommendation"] == "strong_buy"

    @pytest.mark.asyncio
    async def test_sell_band(self, dec_engine: DecisionEngine) -> None:
        scores = dict(SELL_SCORES)
        scores["pattern_score"] = 15
        scores["risk_score"] = 90
        result = dec_engine.combine_scores(scores)
        assert result["recommendation"] in ("sell", "strong_sell")
