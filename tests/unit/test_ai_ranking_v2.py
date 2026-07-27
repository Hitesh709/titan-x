from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.ai_ranking_v2 import AIRankingV2, RankingModelWeight
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.ranking import StockRanking
from titan_x.models.regime import MarketRegime
from titan_x.services.ai_ranking_v2_service import AIRankingServiceV2

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
    return AIRankingServiceV2(session)


@pytest_asyncio.fixture
async def seed_data(session):
    today = date.today()
    c1 = Company(symbol="TEST", company_name="Test Corp", isin="US1234567890",
                 sector="Technology", exchange="NYSE", status="active")
    c2 = Company(symbol="DEMO", company_name="Demo Inc", isin="US0987654321",
                 sector="Healthcare", exchange="NYSE", status="active")
    session.add_all([c1, c2])

    sr1 = StockRanking(as_of_date=today, rank=1, symbol="TEST", composite_score=80.0,
                       financial_health_score=80.0, valuation_score=70.0,
                       momentum_score=75.0, corporate_score=65.0,
                       tier="top_5")
    sr2 = StockRanking(as_of_date=today, rank=2, symbol="DEMO", composite_score=60.0,
                       financial_health_score=60.0, valuation_score=55.0,
                       momentum_score=50.0, corporate_score=45.0,
                       tier="top_10")
    session.add_all([sr1, sr2])

    for i in range(60):
        dp = DailyPrice(symbol="TEST", trade_date=today - timedelta(days=(59 - i)),
                        open=100 + i * 0.5, high=101 + i * 0.5, low=99 + i * 0.5,
                        close=100 + i * 0.5, volume=1_000_000)
        session.add(dp)
        dp2 = DailyPrice(symbol="DEMO", trade_date=today - timedelta(days=(59 - i)),
                         open=50 + i * 0.3, high=51 + i * 0.3, low=49 + i * 0.3,
                         close=50 + i * 0.3, volume=500_000)
        session.add(dp2)

    await session.flush()


class TestRankAll:
    async def test_rank_all(self, service, seed_data):
        rankings = await service.rank_all()
        assert len(rankings) >= 2
        assert rankings[0].rank == 1
        assert rankings[0].weighted_ai_score > 0

    async def test_rank_all_no_companies(self, service):
        rankings = await service.rank_all()
        assert rankings == []

    async def test_rank_all_sets_tier(self, service, seed_data):
        rankings = await service.rank_all()
        for r in rankings:
            assert r.tier in ("top_5", "top_10", "top_25", "top_50", "top_100", "unranked")

    async def test_rank_all_sets_regime(self, service, seed_data):
        rankings = await service.rank_all()
        for r in rankings:
            assert r.market_regime is not None

    async def test_rank_all_sets_weights(self, service, seed_data):
        rankings = await service.rank_all()
        for r in rankings:
            assert r.dynamic_weight_technical is not None
            assert r.dynamic_weight_fundamental is not None

    async def test_rank_all_has_explanation(self, service, seed_data):
        rankings = await service.rank_all()
        for r in rankings:
            assert r.explanation_json is not None


class TestGetRanking:
    async def test_get_ranking(self, service, seed_data):
        await service.rank_all()
        ranking = await service.get_ranking("TEST")
        assert ranking is not None
        assert ranking.symbol == "TEST"

    async def test_get_ranking_not_found(self, service):
        ranking = await service.get_ranking("NONEXIST")
        assert ranking is None

    async def test_get_top(self, service, seed_data):
        await service.rank_all()
        top = await service.get_top(limit=5)
        assert len(top) <= 5


class TestModelWeights:
    async def test_store_weights(self, service, seed_data):
        await service.rank_all()
        weights = await service.get_weights()
        assert len(weights) > 0

    async def test_weights_have_all_fields(self, service, seed_data):
        await service.rank_all()
        weights = await service.get_weights()
        if weights:
            w = weights[0]
            assert w.weight_technical > 0
            assert w.weight_fundamental > 0
            assert w.weight_sentiment > 0
            assert w.weight_momentum > 0


class TestHelpers:
    def test_assign_tier(self, service):
        assert service._assign_tier(1) == "top_5"
        assert service._assign_tier(5) == "top_5"
        assert service._assign_tier(6) == "top_10"
        assert service._assign_tier(11) == "top_25"
        assert service._assign_tier(26) == "top_50"
        assert service._assign_tier(51) == "top_100"
        assert service._assign_tier(101) == "unranked"

    def test_compute_model_confidence(self, service):
        conf = service._compute_model_confidence(80, 70, 60, 50)
        assert 0.1 <= conf <= 1.0

    def test_compute_model_confidence_none(self, service):
        conf = service._compute_model_confidence(None, None)
        assert conf == 0.5
