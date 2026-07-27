from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.price import DailyPrice
from titan_x.models.historical_similarity import SimilarityAnalysis, SimilarityMatch
from titan_x.services.historical_similarity_engine import HistoricalSimilarityEngine


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
async def sim_engine(session: AsyncSession) -> HistoricalSimilarityEngine:
    return HistoricalSimilarityEngine(session)


def _seed_price_data(
    session: AsyncSession, symbol: str = "TEST",
    base_date: date = date(2020, 1, 1), num_days: int = 1500,
) -> None:
    prices: list[DailyPrice] = []
    base_close = 100.0
    for i in range(num_days):
        d = base_date + timedelta(days=i)
        trend = (i / num_days) * 20
        cycle = 10 * (i % 30) / 30
        noise = (i % 7) * 0.3
        close = base_close + trend + cycle + noise
        prices.append(DailyPrice(
            symbol=symbol, trade_date=d,
            open=close - 0.5, high=close + 1.5, low=close - 1.5,
            close=round(close, 2), volume=100000 + (i % 50) * 1000,
        ))
    for p in prices:
        session.add(p)


class TestSimilarityMath:
    @pytest.mark.asyncio
    async def test_normalize(self, sim_engine: HistoricalSimilarityEngine) -> None:
        result = sim_engine._normalize([10, 20, 30])
        assert abs(result[0]) < 0.001
        assert abs(result[2] - 1.0) < 0.001
        assert 0 <= result[1] <= 1

    @pytest.mark.asyncio
    async def test_normalize_flat(self, sim_engine: HistoricalSimilarityEngine) -> None:
        result = sim_engine._normalize([25, 25, 25])
        assert all(v == 0.5 for v in result)

    @pytest.mark.asyncio
    async def test_normalize_empty(self, sim_engine: HistoricalSimilarityEngine) -> None:
        assert sim_engine._normalize([]) == []

    @pytest.mark.asyncio
    async def test_pearson_correlation(self, sim_engine: HistoricalSimilarityEngine) -> None:
        a = [1, 2, 3, 4, 5]
        b = [2, 4, 6, 8, 10]
        corr = sim_engine._pearson_correlation(a, b)
        assert abs(corr - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_pearson_inverse(self, sim_engine: HistoricalSimilarityEngine) -> None:
        a = [1, 2, 3, 4, 5]
        b = [10, 8, 6, 4, 2]
        corr = sim_engine._pearson_correlation(a, b)
        assert abs(corr - (-1.0)) < 0.001

    @pytest.mark.asyncio
    async def test_euclidean_similarity(self, sim_engine: HistoricalSimilarityEngine) -> None:
        a = [0.0, 0.5, 1.0]
        b = [0.0, 0.5, 1.0]
        sim = sim_engine._euclidean_similarity(a, b)
        assert abs(sim - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_euclidean_similarity_different(self, sim_engine: HistoricalSimilarityEngine) -> None:
        a = [0.0, 0.0, 0.0]
        b = [1.0, 1.0, 1.0]
        sim = sim_engine._euclidean_similarity(a, b)
        assert 0 < sim < 1

    @pytest.mark.asyncio
    async def test_volume_similarity(self, sim_engine: HistoricalSimilarityEngine) -> None:
        sim = sim_engine._volume_similarity([100, 200, 300], [100, 200, 300])
        assert abs(sim - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_compute_similarity(self, sim_engine: HistoricalSimilarityEngine) -> None:
        q = [0.0, 0.5, 1.0, 0.5, 0.0]
        h = [0.0, 0.5, 1.0, 0.5, 0.0]
        qv = [100, 200, 300, 200, 100]
        hv = [100, 200, 300, 200, 100]
        result = sim_engine._compute_similarity(q, h, qv, hv)
        assert 0 < result["score"] <= 1.0
        assert abs(result["correlation"] - 1.0) < 0.01


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_self_match(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()

        result = await sim_engine.search("TEST", date(2024, 1, 1), window_days=20, lookback_days=500)
        assert result["symbol"] == "TEST"
        assert "matches" in result
        if result.get("matches"):
            m = result["matches"][0]
            assert "similarity_score" in m
            assert m["similarity_score"] > 0

    @pytest.mark.asyncio
    async def test_search_with_statistics(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()

        result = await sim_engine.search("TEST", date(2023, 6, 1), window_days=15, lookback_days=500, max_matches=10)
        stats = result.get("statistics")
        if stats:
            assert "avg_similarity" in stats
            assert "best_similarity" in stats

    @pytest.mark.asyncio
    async def test_search_forward_returns(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()

        result = await sim_engine.search("TEST", date(2023, 12, 31), window_days=10, lookback_days=300, max_matches=5)
        if result.get("matches"):
            m = result["matches"][0]
            assert "forward_return_1d" in m
            assert "forward_return_5d" in m
            assert "forward_return_10d" in m
            assert "forward_return_20d" in m

    @pytest.mark.asyncio
    async def test_search_insufficient_data(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session, num_days=30)
        await session.flush()

        result = await sim_engine.search("TEST", date(2020, 2, 1), window_days=50)
        assert "error" in result
        assert result["matches"] == []

    @pytest.mark.asyncio
    async def test_search_min_similarity_filter(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()

        result_high = await sim_engine.search("TEST", date(2023, 6, 1), window_days=20, lookback_days=500, min_similarity=0.99)
        result_low = await sim_engine.search("TEST", date(2023, 6, 1), window_days=20, lookback_days=500, min_similarity=0.0)
        assert len(result_high.get("matches", [])) <= len(result_low.get("matches", []))


class TestStatistics:
    @pytest.mark.asyncio
    async def test_compute_statistics(self, sim_engine: HistoricalSimilarityEngine) -> None:
        matches = [
            {"similarity_score": 0.9, "forward_return_1d": 1.0, "forward_return_5d": 2.0, "forward_return_10d": 3.0, "forward_return_20d": 4.0, "forward_return_60d": 5.0},
            {"similarity_score": 0.8, "forward_return_1d": 0.5, "forward_return_5d": 1.5, "forward_return_10d": 2.5, "forward_return_20d": 3.5, "forward_return_60d": 4.5},
        ]
        stats = sim_engine._compute_statistics(matches)
        assert stats["total_matches"] == 2
        assert stats["avg_similarity"] == 0.85
        assert stats["best_similarity"] == 0.9
        assert stats["worst_similarity"] == 0.8
        assert stats["avg_return_1d"] is not None

    @pytest.mark.asyncio
    async def test_compute_statistics_empty(self, sim_engine: HistoricalSimilarityEngine) -> None:
        assert sim_engine._compute_statistics([]) == {}

    @pytest.mark.asyncio
    async def test_optimal_holding_period(self, sim_engine: HistoricalSimilarityEngine) -> None:
        matches = [
            {"similarity_score": 0.9, "forward_return_1d": 1.0, "forward_return_5d": 5.0, "forward_return_10d": 3.0, "forward_return_20d": 2.0, "forward_return_60d": 1.0},
            {"similarity_score": 0.8, "forward_return_1d": 0.5, "forward_return_5d": 4.0, "forward_return_10d": 2.0, "forward_return_20d": 1.0, "forward_return_60d": 0.5},
        ]
        stats = sim_engine._compute_statistics(matches)
        assert stats["optimal_holding_period"] == 5


class TestStoreAndRetrieve:
    @pytest.mark.asyncio
    async def test_store_analysis(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()

        result = await sim_engine.search("TEST", date(2023, 6, 1), window_days=15, lookback_days=500, max_matches=5, store=True)
        assert result.get("statistics") is not None

        analyses, total = await sim_engine.get_analyses("TEST")
        assert total > 0
        assert analyses[0].symbol == "TEST"

    @pytest.mark.asyncio
    async def test_get_analysis_by_id(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()
        await sim_engine.search("TEST", date(2023, 6, 1), window_days=15, lookback_days=500, max_matches=5, store=True)

        analyses, total = await sim_engine.get_analyses("TEST")
        if total > 0:
            analysis = await sim_engine.get_analysis_by_id(analyses[0].id)
            assert analysis is not None
            assert analysis.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_get_matches_for_analysis(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()
        await sim_engine.search("TEST", date(2023, 6, 1), window_days=15, lookback_days=500, max_matches=5, store=True)

        analyses, total = await sim_engine.get_analyses("TEST")
        if total > 0:
            matches, mtotal = await sim_engine.get_matches_for_analysis(analyses[0].id)
            assert mtotal > 0
            assert len(matches) <= 5

    @pytest.mark.asyncio
    async def test_delete_analysis(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()
        await sim_engine.search("TEST", date(2023, 6, 1), window_days=15, lookback_days=500, max_matches=3, store=True)

        analyses, total = await sim_engine.get_analyses("TEST")
        if total > 0:
            aid = analyses[0].id
            deleted = await sim_engine.delete_analysis(aid)
            assert deleted is True
            deleted2 = await sim_engine.delete_analysis(aid)
            assert deleted2 is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_analysis(self, sim_engine: HistoricalSimilarityEngine) -> None:
        assert await sim_engine.delete_analysis(99999) is False


class TestCrossSymbol:
    @pytest.mark.asyncio
    async def test_search_cross_symbol(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session, symbol="TEST")
        _seed_price_data(session, symbol="OTHER")
        await session.flush()

        result = await sim_engine.search_cross_symbol(
            "TEST", ["OTHER"], date(2023, 6, 1),
            window_days=15, lookback_days=300, max_matches=5,
        )
        assert result["symbol"] == "TEST"
        assert "matches_by_symbol" in result
        assert "OTHER" in result["matches_by_symbol"]


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_no_prices(self, sim_engine: HistoricalSimilarityEngine) -> None:
        result = await sim_engine.search("NODATA", date(2024, 1, 1), window_days=20)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_forward_return_for_match(
        self, sim_engine: HistoricalSimilarityEngine, session: AsyncSession,
    ) -> None:
        _seed_price_data(session)
        await session.flush()

        forward = await sim_engine._compute_forward_returns_for_match("TEST", date(2023, 1, 1), date(2024, 1, 1))
        assert "forward_return_1d" in forward
        assert "forward_return_5d" in forward
        assert "forward_return_10d" in forward
        assert "forward_return_20d" in forward
        assert "forward_return_60d" in forward
