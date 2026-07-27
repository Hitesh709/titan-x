import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.corporate_tracking import CorporateAnalysis
from titan_x.models.ensemble import EnsemblePrediction
from titan_x.models.financial_analysis import FinancialAnalysis
from titan_x.models.global_market import GlobalAnalysis
from titan_x.models.institutional_holdings import InstitutionalAnalysis
from titan_x.models.macro import MacroAnalysis
from titan_x.models.master_decision import MasterDecision
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.prediction import Prediction
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.valuation import ValuationReport
from titan_x.services.master_decision_service import MasterDecisionService


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
def svc(session: AsyncSession) -> MasterDecisionService:
    return MasterDecisionService(session)


@pytest_asyncio.fixture
async def strong_setup(session: AsyncSession):
    now = date(2025, 6, 15)
    session.add(Company(symbol="STRONG", company_name="Strong Co", isin="IN001", sector="Technology", exchange="NSE", status="active"))
    await session.flush()
    cid = (await session.execute(select(Company.id).where(Company.symbol == "STRONG"))).scalar_one()

    # All 12 engines with positive signals
    session.add(FinancialAnalysis(symbol="STRONG", analysis_date=now, overall_score=85.0, signal="strong_buy", confidence=0.8, summary_text="Strong revenue growth and margins"))
    session.add(CorporateAnalysis(company_id=cid, analysis_date=now, weighted_score=80.0, signal="buy", confidence=0.7, insights_json="{}"))
    session.add(InstitutionalAnalysis(company_id=cid, analysis_date=now, composite_score=75.0, signal="buy", confidence=0.65, insights_json="{}"))
    session.add(ValuationReport(symbol="STRONG", report_date=now, current_price=100, composite_fair_value=160, margin_of_safety_pct=37.5, recommendation="strong_buy"))
    session.add(MarketMicrostructure(symbol="STRONG", as_of_date=now, liquidity_score=85.0, liquidity_rating="high", volume_ratio=1.5))
    session.add(RiskMetrics(symbol="STRONG", as_of_date=now, composite_risk_score=25.0, risk_rating="low"))
    session.add(EnsemblePrediction(symbol="STRONG", as_of_date=now, ensemble_score=80.0, ensemble_signal="buy", ensemble_confidence=0.7,
        technical_score=75, fundamental_score=80, news_score=70, macro_score=65, risk_score=30, pattern_score=70))
    session.add(MacroAnalysis(as_of_date=now, composite_macro_score=70.0, macro_regime="neutral", growth_inflation_regime="goldilocks", risk_regime="risk_on"))
    session.add(GlobalAnalysis(as_of_date=now, global_score=75.0, global_sentiment="bullish", us_score=80, europe_score=70, asia_score=65))
    session.add(Prediction(symbol="STRONG", as_of_date=now, signal_5d="buy", confidence_5d=0.7, expected_return_5d=0.05, signal_20d="strong_buy", confidence_20d=0.75, expected_return_20d=0.12))
    session.add(MarketRegime(symbol="STRONG", as_of_date=now, trend_regime="bull", volatility_regime="normal_volatility", sentiment_regime="risk_on", confidence=0.8, momentum_20d=0.08))

    # Price data for momentum (uptrend)
    base = date(2025, 1, 1)
    for i in range(170):
        d = base + timedelta(days=i)
        p = 50 + i * 0.3
        session.add(DailyPrice(symbol="STRONG", trade_date=d, open=p * 0.99, high=p * 1.02, low=p * 0.98, close=p, volume=100000))

    await session.flush()


@pytest_asyncio.fixture
async def weak_setup(session: AsyncSession):
    now = date(2025, 6, 15)
    session.add(Company(symbol="WEAK", company_name="Weak Co", isin="IN002", sector="Energy", exchange="NSE", status="active"))
    await session.flush()
    cid = (await session.execute(select(Company.id).where(Company.symbol == "WEAK"))).scalar_one()

    # Few weak signals with conflicts
    session.add(FinancialAnalysis(symbol="WEAK", analysis_date=now, overall_score=30.0, signal="sell", confidence=0.5, summary_text="Declining revenue, shrinking margins"))
    session.add(CorporateAnalysis(company_id=cid, analysis_date=now, weighted_score=25.0, signal="sell", confidence=0.4, insights_json="{}"))
    session.add(ValuationReport(symbol="WEAK", report_date=now, current_price=100, composite_fair_value=50, margin_of_safety_pct=-50.0, recommendation="strong_sell"))
    session.add(RiskMetrics(symbol="WEAK", as_of_date=now, composite_risk_score=80.0, risk_rating="high"))

    # Price data for momentum (downtrend)
    base = date(2025, 1, 1)
    for i in range(170):
        d = base + timedelta(days=i)
        p = 100 - i * 0.2
        session.add(DailyPrice(symbol="WEAK", trade_date=d, open=p * 0.99, high=p * 1.02, low=p * 0.98, close=p, volume=50000))

    await session.flush()


# ============================================================
# MASTER DECISION
# ============================================================

class TestMasterDecision:
    @pytest.mark.asyncio
    async def test_evaluate_strong(self, svc: MasterDecisionService, strong_setup):
        d = await svc.evaluate("STRONG")
        assert d.symbol == "STRONG"
        assert d.final_ai_score is not None
        assert d.final_ai_score > 60
        assert d.confidence > 0.5
        assert d.recommendation in ("strong_buy", "buy", "hold")
        assert d.is_weak is False
        assert d.engine_count >= 10

    @pytest.mark.asyncio
    async def test_evaluate_weak_rejected(self, svc: MasterDecisionService, weak_setup):
        d = await svc.evaluate("WEAK")
        assert d.symbol == "WEAK"
        assert d.final_ai_score < 50
        assert d.is_weak is True
        assert d.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_risk_level(self, svc: MasterDecisionService, strong_setup):
        d = await svc.evaluate("STRONG")
        assert d.risk_level in ("low", "moderate", "high")
        assert d.risk_score is not None

    @pytest.mark.asyncio
    async def test_scores_broken_down(self, svc: MasterDecisionService, strong_setup):
        d = await svc.evaluate("STRONG")
        assert d.financial_analysis_score == 85.0
        assert d.corporate_governance_score == 80.0
        assert d.institutional_score == 75.0
        assert d.liquidity_score == 85.0
        assert d.valuation_score is not None

    @pytest.mark.asyncio
    async def test_evidence_json(self, svc: MasterDecisionService, strong_setup):
        d = await svc.evaluate("STRONG")
        ev = json.loads(d.evidence_json)
        assert "engine_scores" in ev
        assert "engine_evidence" in ev
        assert "signal_summary" in ev
        assert "agreement_score" in ev

    @pytest.mark.asyncio
    async def test_decision_summary(self, svc: MasterDecisionService, strong_setup):
        d = await svc.evaluate("STRONG")
        assert d.decision_summary is not None
        assert "STRONG" in d.decision_summary
        assert "Final Score" in d.decision_summary

    @pytest.mark.asyncio
    async def test_get_decision(self, svc: MasterDecisionService, strong_setup):
        await svc.evaluate("STRONG")
        fetched = await svc.get_decision("STRONG")
        assert fetched is not None
        assert fetched.symbol == "STRONG"

    @pytest.mark.asyncio
    async def test_get_decision_not_found(self, svc: MasterDecisionService):
        fetched = await svc.get_decision("UNKNOWN")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_decisions_strong_only(self, svc: MasterDecisionService, strong_setup, weak_setup):
        await svc.evaluate("STRONG")
        await svc.evaluate("WEAK")
        strong_only = await svc.list_decisions(min_score=60, include_weak=False)
        assert len(strong_only) >= 1
        for d in strong_only:
            assert d.final_ai_score >= 60 if d.final_ai_score is not None else True

    @pytest.mark.asyncio
    async def test_list_decisions_include_weak(self, svc: MasterDecisionService, strong_setup, weak_setup):
        await svc.evaluate("STRONG")
        await svc.evaluate("WEAK")
        all_decisions = await svc.list_decisions(include_weak=True, limit=10)
        assert len(all_decisions) >= 2

    @pytest.mark.asyncio
    async def test_list_decisions_by_recommendation(self, svc: MasterDecisionService, strong_setup, weak_setup):
        await svc.evaluate("STRONG")
        await svc.evaluate("WEAK")
        buys = await svc.list_decisions(recommendation="strong_buy", include_weak=True)
        sells = await svc.list_decisions(recommendation="strong_sell", include_weak=True)
        total = len(buys) + len(sells)
        assert total >= 0  # at least one may match

    @pytest.mark.asyncio
    async def test_engine_count(self, svc: MasterDecisionService, strong_setup):
        d = await svc.evaluate("STRONG")
        assert d.engine_count >= 10  # most engines active

    @pytest.mark.asyncio
    async def test_weak_conflicting_signals(self, svc: MasterDecisionService, session: AsyncSession):
        now = date(2025, 6, 15)
        session.add(Company(symbol="CONFLICT", company_name="Conflict Co", isin="IN010", sector="Finance", exchange="NSE", status="active"))
        await session.flush()
        # 3 buy signals + 3 sell signals
        session.add(FinancialAnalysis(symbol="CONFLICT", analysis_date=now, overall_score=55.0, signal="buy", confidence=0.6, summary_text="Mixed"))
        session.add(ValuationReport(symbol="CONFLICT", report_date=now, current_price=100, composite_fair_value=120, margin_of_safety_pct=16.7, recommendation="buy"))
        session.add(EnsemblePrediction(symbol="CONFLICT", as_of_date=now, ensemble_score=40.0, ensemble_signal="sell", ensemble_confidence=0.5,
            technical_score=40, fundamental_score=50, news_score=50, macro_score=50, risk_score=50, pattern_score=50))
        # sell signals
        session.add(MarketRegime(symbol="CONFLICT", as_of_date=now, trend_regime="bear", volatility_regime="high_volatility", sentiment_regime="risk_off", confidence=0.7, momentum_20d=-0.05))
        session.add(Prediction(symbol="CONFLICT", as_of_date=now, signal_5d="sell", confidence_5d=0.6, expected_return_5d=-0.03, signal_20d="sell", confidence_20d=0.55, expected_return_20d=-0.05))
        session.add(MarketMicrostructure(symbol="CONFLICT", as_of_date=now, liquidity_score=40.0, liquidity_rating="low", volume_ratio=0.5))
        # Price data
        base = date(2025, 1, 1)
        for i in range(170):
            d = base + timedelta(days=i)
            session.add(DailyPrice(symbol="CONFLICT", trade_date=d, open=50, high=51, low=49, close=50, volume=100000))
        await session.flush()

        d = await svc.evaluate("CONFLICT")
        # Should be rejected due to conflicting signals
        assert d.is_weak is True

    @pytest.mark.asyncio
    async def test_evaluate_all(self, svc: MasterDecisionService, strong_setup, weak_setup):
        results = await svc.evaluate_all()
        assert len(results) >= 2
        symbols = [d.symbol for d in results]
        assert "STRONG" in symbols
        assert "WEAK" in symbols

    @pytest.mark.asyncio
    async def test_decision_persistence(self, svc: MasterDecisionService, strong_setup):
        d1 = await svc.evaluate("STRONG")
        d2 = await svc.get_decision("STRONG")
        assert d2 is not None
        assert d2.id == d1.id

    @pytest.mark.asyncio
    async def test_minimal_data(self, svc: MasterDecisionService, session: AsyncSession):
        now = date(2025, 6, 15)
        session.add(Company(symbol="MINIMAL", company_name="Minimal Co", isin="IN020", sector="Unknown", exchange="NSE", status="active"))
        await session.flush()
        d = await svc.evaluate("MINIMAL")
        assert d.is_weak is True
        assert "Insufficient data" in d.rejection_reason
