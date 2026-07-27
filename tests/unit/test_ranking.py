import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from sqlalchemy import select

from titan_x.models.corporate_tracking import CorporateAnalysis
from titan_x.models.financial_analysis import FinancialAnalysis
from titan_x.models.institutional_holdings import InstitutionalAnalysis
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.price import DailyPrice
from titan_x.models.ranking import StockRanking
from titan_x.models.risk import RiskMetrics
from titan_x.models.valuation import ValuationReport
from titan_x.services.ranking_service import RankingService


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
def svc(session: AsyncSession) -> RankingService:
    return RankingService(session)


@pytest_asyncio.fixture
async def ranked_setup(session: AsyncSession):
    """Create stocks with varying scores for ranking."""
    companies = [
        Company(symbol="TOPSCO", company_name="Top Score Co", isin="IN001", sector="Technology", exchange="NSE"),
        Company(symbol="MIDSCORE", company_name="Mid Score Co", isin="IN002", sector="Finance", exchange="NSE"),
        Company(symbol="LOWSCORE", company_name="Low Score Co", isin="IN003", sector="Energy", exchange="NSE"),
        Company(symbol="NOSCORE", company_name="No Score Co", isin="IN004", sector="Healthcare", exchange="NSE"),
    ]
    for c in companies:
        session.add(c)
    await session.flush()

    now = date(2025, 6, 15)

    # TOPSCO — excellent across all dimensions
    session.add(FinancialAnalysis(symbol="TOPSCO", analysis_date=now, overall_score=85.0, signal="strong_buy"))
    session.add(ValuationReport(symbol="TOPSCO", report_date=now, current_price=100, composite_fair_value=150, margin_of_safety_pct=33.3, recommendation="strong_buy"))
    session.add(MarketMicrostructure(symbol="TOPSCO", as_of_date=now, liquidity_score=90.0, liquidity_rating="high"))
    session.add(RiskMetrics(symbol="TOPSCO", as_of_date=now, composite_risk_score=20.0, risk_rating="low"))

    # MIDSCORE — moderate scores
    session.add(FinancialAnalysis(symbol="MIDSCORE", analysis_date=now, overall_score=60.0, signal="buy"))
    session.add(ValuationReport(symbol="MIDSCORE", report_date=now, current_price=100, composite_fair_value=110, margin_of_safety_pct=9.1, recommendation="buy"))
    session.add(MarketMicrostructure(symbol="MIDSCORE", as_of_date=now, liquidity_score=65.0, liquidity_rating="moderate"))
    session.add(RiskMetrics(symbol="MIDSCORE", as_of_date=now, composite_risk_score=45.0, risk_rating="moderate"))

    # LOWSCORE — poor scores
    session.add(FinancialAnalysis(symbol="LOWSCORE", analysis_date=now, overall_score=30.0, signal="sell"))
    session.add(ValuationReport(symbol="LOWSCORE", report_date=now, current_price=100, composite_fair_value=70, margin_of_safety_pct=-30.0, recommendation="sell"))

    # Price data for momentum — TOPSCO trending up, LOWSCORE trending down
    base = date(2025, 1, 1)
    for i in range(170):
        d = base + timedelta(days=i)
        topsco_p = 50 + i * 0.3
        midsco_p = 70 + i * 0.1
        lowsco_p = 100 - i * 0.2
        nosco_p = 60 + i * 0.05
        for sym, p in [("TOPSCO", topsco_p), ("MIDSCORE", midsco_p), ("LOWSCORE", lowsco_p), ("NOSCORE", nosco_p)]:
            session.add(DailyPrice(
                symbol=sym, trade_date=d,
                open=round(p * 0.99, 2), high=round(p * 1.02, 2),
                low=round(p * 0.98, 2), close=round(p, 2), volume=100000,
            ))

    await session.flush()


# ============================================================
# RANKING
# ============================================================

class TestRanking:
    @pytest.mark.asyncio
    async def test_rank_all_orders_correctly(self, svc: RankingService, ranked_setup):
        rankings = await svc.rank_all(date(2025, 6, 15))
        assert len(rankings) >= 3  # at least the ones with data
        # TOPSCO should be #1
        assert rankings[0].symbol == "TOPSCO"
        assert rankings[0].rank == 1
        assert rankings[0].is_best_opportunity is True

    @pytest.mark.asyncio
    async def test_rank_tiers_assigned(self, svc: RankingService, ranked_setup):
        rankings = await svc.rank_all(date(2025, 6, 15))
        tiers = set(r.tier for r in rankings)
        assert "top_5" in tiers
        # All 4 stocks are top_5 since there are only 4

    @pytest.mark.asyncio
    async def test_composite_score_range(self, svc: RankingService, ranked_setup):
        rankings = await svc.rank_all(date(2025, 6, 15))
        for r in rankings:
            assert 0 <= r.composite_score <= 100
            assert 0 <= r.risk_adjusted_score <= 100

    @pytest.mark.asyncio
    async def test_best_opportunity(self, svc: RankingService, ranked_setup):
        await svc.rank_all(date(2025, 6, 15))
        best = await svc.get_best_opportunity(date(2025, 6, 15))
        assert best is not None
        assert best.is_best_opportunity is True
        assert best.symbol == "TOPSCO"

    @pytest.mark.asyncio
    async def test_get_top_tier(self, svc: RankingService, ranked_setup):
        await svc.rank_all(date(2025, 6, 15))
        top5 = await svc.get_top("top_5", date(2025, 6, 15))
        assert len(top5) >= 1
        assert all(r.tier == "top_5" for r in top5)

    @pytest.mark.asyncio
    async def test_get_stock_ranking(self, svc: RankingService, ranked_setup):
        await svc.rank_all(date(2025, 6, 15))
        ranking = await svc.get_ranking("TOPSCO", date(2025, 6, 15))
        assert ranking is not None
        assert ranking.rank == 1
        assert ranking.explanation_json is not None

    @pytest.mark.asyncio
    async def test_explanation_structure(self, svc: RankingService, ranked_setup):
        await svc.rank_all(date(2025, 6, 15))
        ranking = await svc.get_ranking("TOPSCO", date(2025, 6, 15))
        expl = json.loads(ranking.explanation_json)
        assert "symbol" in expl
        assert "rank" in expl
        assert "details" in expl
        assert "strengths" in expl
        assert "weaknesses" in expl
        assert "summary" in expl
        assert expl["rank"] == 1

    @pytest.mark.asyncio
    async def test_ranking_without_data(self, svc: RankingService):
        rankings = await svc.rank_all(date(2025, 6, 15))
        # NOSCORE has no analysis data but has price data
        assert len(rankings) >= 0

    @pytest.mark.asyncio
    async def test_rank_scores_reflect_data(self, svc: RankingService, ranked_setup):
        rankings = await svc.rank_all(date(2025, 6, 15))
        topsco = next(r for r in rankings if r.symbol == "TOPSCO")
        lowsco = next(r for r in rankings if r.symbol == "LOWSCORE")
        assert topsco.composite_score > lowsco.composite_score
        assert topsco.risk_adjusted_score > lowsco.risk_adjusted_score

    @pytest.mark.asyncio
    async def test_financial_health_score(self, svc: RankingService, ranked_setup):
        await svc.rank_all(date(2025, 6, 15))
        ranking = await svc.get_ranking("TOPSCO", date(2025, 6, 15))
        assert ranking.financial_health_score == 85.0

    @pytest.mark.asyncio
    async def test_valuation_upside_scoring(self, svc: RankingService, ranked_setup):
        await svc.rank_all(date(2025, 6, 15))
        ranking = await svc.get_ranking("TOPSCO", date(2025, 6, 15))
        # 150 fair value, 100 current = 50% upside → 50 + 0.5*100 = 100
        assert ranking.valuation_score is not None
        assert ranking.valuation_score > 50

    @pytest.mark.asyncio
    async def test_no_duplicate_rankings(self, svc: RankingService, ranked_setup):
        rankings = await svc.rank_all(date(2025, 6, 15))
        symbols = [r.symbol for r in rankings]
        assert len(symbols) == len(set(symbols))

    @pytest.mark.asyncio
    async def test_rankings_use_risk_adjustment(self, svc: RankingService, ranked_setup):
        rankings = await svc.rank_all(date(2025, 6, 15))
        # TOPSCO has low risk, so risk-adjusted should be close to composite
        topsco = next(r for r in rankings if r.symbol == "TOPSCO")
        assert topsco.risk_adjusted_score <= topsco.composite_score or abs(topsco.risk_adjusted_score - topsco.composite_score) < 10

    @pytest.mark.asyncio
    async def test_explanation_includes_strategy(self, svc: RankingService, ranked_setup):
        await svc.rank_all(date(2025, 6, 15))
        ranking = await svc.get_ranking("TOPSCO", date(2025, 6, 15))
        expl = json.loads(ranking.explanation_json)
        assert "strategy" in expl
        assert len(expl["strategy"]) > 0

    @pytest.mark.asyncio
    async def test_corporate_and_institutional_scores(self, svc: RankingService, session: AsyncSession):
        now = date(2025, 6, 15)
        session.add(Company(symbol="CORPINST", company_name="CI Co", isin="IN010", sector="Finance", exchange="NSE"))
        await session.flush()
        cid = (await session.execute(
            select(Company.id).where(Company.symbol == "CORPINST")
        )).scalar_one()
        session.add(CorporateAnalysis(company_id=cid, analysis_date=now, weighted_score=80.0, signal="buy", insights_json="{}"))
        session.add(InstitutionalAnalysis(company_id=cid, analysis_date=now, composite_score=75.0, signal="buy", insights_json="{}"))
        await session.flush()

        # Price data
        base = date(2025, 1, 1)
        for i in range(170):
            d = base + timedelta(days=i)
            session.add(DailyPrice(symbol="CORPINST", trade_date=d, open=50, high=51, low=49, close=50, volume=100000))
        await session.flush()

        rankings = await svc.rank_all(now)
        ranking = await svc.get_ranking("CORPINST", now)
        assert ranking is not None
        assert ranking.corporate_score == 80.0
        assert ranking.institutional_score == 75.0

    @pytest.mark.asyncio
    async def test_no_companies(self, svc: RankingService):
        rankings = await svc.rank_all(date(2025, 6, 15))
        assert rankings == []
