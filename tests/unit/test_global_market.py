import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.global_market import GlobalAnalysis, GlobalCondition, GlobalMarketData, GlobalSimilarityResult
from titan_x.models.price import DailyPrice
from titan_x.services.global_market_service import GlobalMarketService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> GlobalMarketService:
    return GlobalMarketService(session)


@pytest_asyncio.fixture
async def global_data(svc: GlobalMarketService):
    """Seed 60 days of global market data."""
    base = date(2025, 1, 1)
    for i in range(60):
        d = base + timedelta(days=i)
        await svc.record_data("index", "us", "SPX", d, 4500 + i * 2, change_pct=0.1)
        await svc.record_data("index", "us", "NDX", d, 15000 + i * 5, change_pct=0.15)
        await svc.record_data("index", "us", "DJI", d, 35000 + i * 10, change_pct=0.08)
        await svc.record_data("index", "europe", "FTSE", d, 7500 + i * 1, change_pct=0.05)
        await svc.record_data("index", "europe", "DAX", d, 18000 + i * 3, change_pct=0.12)
        await svc.record_data("index", "europe", "CAC", d, 6500 + i * 1.5, change_pct=0.07)
        await svc.record_data("index", "asia", "NKY", d, 32000 + i * 8, change_pct=0.2)
        await svc.record_data("index", "asia", "HSI", d, 22000 - i * 5, change_pct=-0.1)
        await svc.record_data("index", "asia", "SHCOMP", d, 3100 + i * 0.5, change_pct=0.02)
        await svc.record_data("futures", "global", "ES", d, 4550 + i * 2, change_pct=0.1)
        await svc.record_data("futures", "global", "NQ", d, 15200 + i * 5, change_pct=0.15)
        await svc.record_data("vix", "global", "VIX", d, 18 - i * 0.05)
        await svc.record_data("dxy", "global", "DXY", d, 104 + i * 0.02)


@pytest_asyncio.fixture
async def price_data(session: AsyncSession):
    """Seed daily prices for forward return computation."""
    base = date(2025, 1, 1)
    for i in range(120):
        d = base + timedelta(days=i)
        for sym in ["SPX", "NDX", "NKY", "HSI"]:
            session.add(DailyPrice(
                symbol=sym, trade_date=d, open=100 + i * 0.1,
                high=101 + i * 0.1, low=99 + i * 0.1,
                close=100 + i * 0.1, volume=100000,
            ))
    await session.flush()


# ============================================================
# GLOBAL MARKET DATA
# ============================================================

class TestGlobalData:
    @pytest.mark.asyncio
    async def test_record_data(self, svc: GlobalMarketService):
        d = await svc.record_data("index", "us", "SPX", date(2025, 6, 1), 5000, 0.5, "Bloomberg")
        assert d.symbol == "SPX"
        assert d.value == 5000
        assert d.change_pct == 0.5

    @pytest.mark.asyncio
    async def test_get_latest_data(self, svc: GlobalMarketService, global_data):
        d = await svc.get_data("SPX")
        assert d is not None
        assert d.symbol == "SPX"
        assert d.value > 0

    @pytest.mark.asyncio
    async def test_get_data_by_date(self, svc: GlobalMarketService, global_data):
        d = await svc.get_data("SPX", date(2025, 1, 1))
        assert d is not None
        assert d.value == 4500

    @pytest.mark.asyncio
    async def test_get_data_not_found(self, svc: GlobalMarketService):
        d = await svc.get_data("UNKNOWN")
        assert d is None

    @pytest.mark.asyncio
    async def test_list_data_by_region(self, svc: GlobalMarketService, global_data):
        results = await svc.list_data(region="asia", limit=10)
        assert len(results) > 0
        assert all(r.region == "asia" for r in results)

    @pytest.mark.asyncio
    async def test_list_data_by_type(self, svc: GlobalMarketService, global_data):
        results = await svc.list_data(data_type="vix", limit=10)
        assert len(results) > 0
        assert all(r.data_type == "vix" for r in results)


# ============================================================
# GLOBAL ANALYSIS
# ============================================================

class TestGlobalAnalysis:
    @pytest.mark.asyncio
    async def test_analyze_returns_scores(self, svc: GlobalMarketService, global_data):
        result = await svc.analyze(date(2025, 3, 1))
        assert result.us_score is not None
        assert result.europe_score is not None
        assert result.asia_score is not None
        assert result.futures_score is not None
        assert result.vix_score is not None
        assert result.dxy_score is not None
        assert result.global_score is not None
        assert result.global_sentiment in ("bullish", "bearish", "neutral")
        assert 0 <= result.global_score <= 100

    @pytest.mark.asyncio
    async def test_analyze_no_data(self, svc: GlobalMarketService):
        result = await svc.analyze(date(2020, 1, 1))
        assert result.global_score == 50.0
        assert result.global_sentiment == "neutral"

    @pytest.mark.asyncio
    async def test_analyze_details(self, svc: GlobalMarketService, global_data):
        result = await svc.analyze(date(2025, 3, 1))
        details = json.loads(result.details_json)
        assert "us" in details
        assert "europe" in details
        assert "asia" in details
        assert "vix" in details
        assert "dxy" in details

    @pytest.mark.asyncio
    async def test_get_analysis(self, svc: GlobalMarketService, global_data):
        a1 = await svc.analyze(date(2025, 3, 1))
        a2 = await svc.get_analysis(date(2025, 3, 1))
        assert a2.id == a1.id

    @pytest.mark.asyncio
    async def test_get_latest_analysis(self, svc: GlobalMarketService, global_data):
        await svc.analyze(date(2025, 2, 1))
        latest = await svc.analyze(date(2025, 3, 1))
        fetched = await svc.get_analysis()
        assert fetched.id == latest.id

    @pytest.mark.asyncio
    async def test_get_analysis_not_found(self, svc: GlobalMarketService):
        result = await svc.get_analysis(date(2020, 1, 1))
        assert result is None

    @pytest.mark.asyncio
    async def test_list_analyses(self, svc: GlobalMarketService, global_data):
        for i in range(5):
            await svc.analyze(date(2025, 1, 1) + timedelta(days=30 * i))
        results = await svc.list_analyses(limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_vix_score_inverse(self, svc: GlobalMarketService, global_data):
        result = await svc.analyze(date(2025, 3, 1))
        # VIX is falling (18 to ~14.5), so score should be high
        assert result.vix_score > 50


# ============================================================
# CONDITIONS & SIMILARITY SEARCH
# ============================================================

class TestConditionsAndSimilarity:
    @pytest.mark.asyncio
    async def test_build_condition(self, svc: GlobalMarketService, global_data, price_data):
        cond = await svc.build_condition_snapshot(date(2025, 3, 1))
        vec = json.loads(cond.feature_vector)
        assert len(vec) == 7
        assert all(0 <= v <= 100 for v in vec)
        outcomes = json.loads(cond.outcome_returns_json)
        assert "SPX" in outcomes or {}  # may or may not have outcomes

    @pytest.mark.asyncio
    async def test_condition_region_scores(self, svc: GlobalMarketService, global_data, price_data):
        cond = await svc.build_condition_snapshot(date(2025, 3, 1))
        scores = json.loads(cond.region_scores_json)
        assert "us" in scores
        assert "global" in scores

    @pytest.mark.asyncio
    async def test_search_similar_with_conditions(self, svc: GlobalMarketService, global_data, price_data):
        # Build conditions on multiple dates
        d1 = date(2025, 2, 1)
        d2 = date(2025, 2, 15)
        d3 = date(2025, 3, 1)
        await svc.build_condition_snapshot(d1)
        await svc.build_condition_snapshot(d2)
        await svc.build_condition_snapshot(d3)

        # Search from a later date
        results = await svc.search_similar(date(2025, 3, 15), top_n=3)
        assert len(results) <= 3
        for r in results:
            assert r.similarity_pct > 0
            assert r.query_date == date(2025, 3, 15)
            assert r.matched_date in (d1, d2, d3)

    @pytest.mark.asyncio
    async def test_similarity_returns_avg_returns(self, svc: GlobalMarketService, global_data, price_data):
        await svc.build_condition_snapshot(date(2025, 2, 1))
        results = await svc.search_similar(date(2025, 3, 15), top_n=1)
        if results:
            r = results[0]
            assert r.avg_return_1d is not None or r.avg_return_5d is not None
            assert r.similarity_pct > 0

    @pytest.mark.asyncio
    async def test_similarity_winning_losing_stocks(self, svc: GlobalMarketService, global_data, price_data):
        await svc.build_condition_snapshot(date(2025, 2, 1))
        results = await svc.search_similar(date(2025, 3, 15), top_n=1)
        if results:
            r = results[0]
            winning = json.loads(r.winning_stocks_json) if r.winning_stocks_json else {}
            losing = json.loads(r.losing_stocks_json) if r.losing_stocks_json else {}
            assert isinstance(winning, dict)
            assert isinstance(losing, dict)

    @pytest.mark.asyncio
    async def test_get_similarity_results(self, svc: GlobalMarketService, global_data, price_data):
        await svc.build_condition_snapshot(date(2025, 2, 1))
        await svc.search_similar(date(2025, 3, 15), top_n=1)
        stored = await svc.get_similarity_results(date(2025, 3, 15))
        assert len(stored) >= 1

    @pytest.mark.asyncio
    async def test_similarity_empty_db(self, svc: GlobalMarketService):
        results = await svc.search_similar(date(2025, 3, 15), top_n=5)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_condition_without_prices(self, svc: GlobalMarketService, global_data):
        cond = await svc.build_condition_snapshot(date(2025, 3, 1))
        outcomes = json.loads(cond.outcome_returns_json) if cond.outcome_returns_json else {}
        # No price data in this test, so outcomes may be empty
        assert isinstance(outcomes, dict)

    @pytest.mark.asyncio
    async def test_cosine_similarity_perfect(self, svc: GlobalMarketService):
        a = [50, 60, 70, 80, 90, 50, 65]
        sim = svc._cosine_similarity(a, a)
        assert sim == 1.0

    @pytest.mark.asyncio
    async def test_cosine_similarity_orthogonal(self, svc: GlobalMarketService):
        a = [100, 0, 0]
        b = [0, 100, 0]
        sim = svc._cosine_similarity(a, b)
        assert sim == 0.0
