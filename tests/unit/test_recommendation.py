import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.recommendation import Recommendation
from titan_x.services.recommendation_service import RecommendationService

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
async def seeded_session(session):
    svc = RecommendationService(session)
    await svc.create_recommendation(
        symbol="AAPL", direction="buy", confidence=0.85,
        price_target=250.0, current_price=220.0,
        timeframe="short_term", score=0.88,
        recommendation_type="technical", source="model_v1",
        risk_level="medium", predicted_return_pct=13.6,
        reasoning="Strong RSI breakout",
        inputs_json='{"rsi": 72, "macd": "bullish", "volume_spike": true}',
        model_version_id=1, model_version_label="v1.0",
    )
    await svc.create_recommendation(
        symbol="AAPL", direction="hold", confidence=0.60,
        price_target=240.0, current_price=235.0,
        timeframe="medium_term", score=0.65,
        recommendation_type="fundamental", source="analyst_x",
        risk_level="low", predicted_return_pct=2.1,
        reasoning="Fairly valued",
    )
    await svc.create_recommendation(
        symbol="MSFT", direction="buy", confidence=0.90,
        price_target=500.0, current_price=420.0,
        timeframe="long_term", score=0.92,
        recommendation_type="ml_ensemble", source="model_v2",
        risk_level="medium", predicted_return_pct=19.0,
        reasoning="Cloud growth momentum",
        inputs_json='{"pe_ratio": 35, "revenue_growth": 0.18}',
        model_version_id=2, model_version_label="v2.1",
    )
    await svc.create_recommendation(
        symbol="TSLA", direction="sell", confidence=0.75,
        price_target=150.0, current_price=200.0,
        timeframe="short_term", score=0.72,
        recommendation_type="technical", source="model_v1",
        risk_level="high", predicted_return_pct=-25.0,
        reasoning="Breaking below support",
    )
    return session


# ── Create ──

@pytest.mark.asyncio
class TestCreate:
    async def test_create_recommendation(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(
            symbol="GOOGL", direction="buy", confidence=0.80,
            score=0.85, source="model_v3",
        )
        assert rec.id is not None
        assert rec.symbol == "GOOGL"
        assert rec.direction == "buy"
        assert rec.confidence == 0.80
        assert rec.score == 0.85
        assert rec.source == "model_v3"
        assert rec.status == "active"
        assert rec.generated_at is not None

    async def test_create_uppercases_symbol(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="aapl", direction="buy")
        assert rec.symbol == "AAPL"

    async def test_create_with_tracking_fields(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(
            symbol="NVDA", direction="buy",
            inputs_json='{"pe": 55, "eps_growth": 0.30}',
            model_version_id=3, model_version_label="v3.0",
        )
        assert rec.inputs_json == '{"pe": 55, "eps_growth": 0.30}'
        assert rec.model_version_id == 3
        assert rec.model_version_label == "v3.0"
        assert rec.decision == "pending"
        assert rec.outcome == "pending"

    async def test_get_recommendation(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="TEST", direction="buy")
        got = await svc.get_recommendation(rec.id)
        assert got is not None and got.id == rec.id

    async def test_get_recommendation_not_found(self, session):
        svc = RecommendationService(session)
        assert await svc.get_recommendation(9999) is None


# ── List ──

@pytest.mark.asyncio
class TestList:
    async def test_list_all(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations()
        assert len(items) == 4

    async def test_list_filter_symbol(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(symbol="AAPL")
        assert len(items) == 2
        assert all(r.symbol == "AAPL" for r in items)

    async def test_list_filter_direction(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(direction="buy")
        assert len(items) == 2
        assert all(r.direction == "buy" for r in items)

    async def test_list_filter_type(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(recommendation_type="technical")
        assert len(items) == 2

    async def test_list_filter_timeframe(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(timeframe="short_term")
        assert len(items) == 2

    async def test_list_filter_min_confidence(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(min_confidence=0.80)
        assert len(items) == 2

    async def test_list_filter_min_score(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(min_score=0.80)
        assert len(items) == 2

    async def test_list_filter_source(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(source="model_v1")
        assert len(items) == 2

    async def test_list_filter_risk_level(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(risk_level="high")
        assert len(items) == 1

    async def test_list_filter_status(self, session):
        svc = RecommendationService(session)
        await svc.create_recommendation(symbol="A", direction="buy", status="active")
        await svc.create_recommendation(symbol="B", direction="sell", status="expired")
        items = await svc.list_recommendations(status="active")
        assert len(items) == 1

    async def test_list_filter_decision(self, seeded_session):
        svc = RecommendationService(seeded_session)
        await svc.set_decision(1, decision="acted", decision_reason="Strong signal")
        items = await svc.list_recommendations(decision="acted")
        assert len(items) == 1
        assert items[0].id == 1

    async def test_list_filter_outcome(self, seeded_session):
        svc = RecommendationService(seeded_session)
        await svc.set_outcome(2, outcome="correct", actual_outcome_pnl=150.0)
        items = await svc.list_recommendations(outcome="correct")
        assert len(items) == 1
        assert items[0].id == 2

    async def test_list_pagination(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(limit=2, offset=0)
        assert len(items) == 2
        items_page2 = await svc.list_recommendations(limit=2, offset=2)
        assert len(items_page2) == 2

    async def test_list_sort_by_score(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.list_recommendations(sort_by="score", sort_desc=True)
        scores = [r.score for r in items if r.score is not None]
        assert scores == sorted(scores, reverse=True)


# ── Top ──

@pytest.mark.asyncio
class TestTop:
    async def test_top_recommendations(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_top_recommendations(limit=2)
        assert len(items) == 2
        assert items[0].score >= items[1].score

    async def test_top_default_active(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_top_recommendations()
        assert all(r.status == "active" for r in items)

    async def test_top_min_score(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_top_recommendations(min_score=0.80)
        assert all(r.score >= 0.80 for r in items)

    async def test_top_returns_all_when_fewer(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_top_recommendations(limit=100)
        assert len(items) == 4


# ── History ──

@pytest.mark.asyncio
class TestHistory:
    async def test_history_by_symbol(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_recommendation_history(symbol="AAPL")
        assert len(items) == 2
        assert all(r.symbol == "AAPL" for r in items)

    async def test_history_empty(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_recommendation_history(symbol="NONE")
        assert len(items) == 0

    async def test_history_pagination(self, seeded_session):
        svc = RecommendationService(seeded_session)
        page1 = await svc.get_recommendation_history(symbol="AAPL", limit=1, offset=0)
        assert len(page1) == 1
        page2 = await svc.get_recommendation_history(symbol="AAPL", limit=1, offset=1)
        assert len(page2) == 1
        assert page1[0].id != page2[0].id


# ── By Symbol ──

@pytest.mark.asyncio
class TestBySymbol:
    async def test_by_symbol_active(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_recommendations_by_symbol(symbol="AAPL")
        assert len(items) == 2
        assert all(r.symbol == "AAPL" for r in items)
        assert all(r.status == "active" for r in items)

    async def test_by_symbol_all_statuses(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_recommendations_by_symbol(symbol="AAPL", status=None)
        assert len(items) == 2

    async def test_by_symbol_not_found(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_recommendations_by_symbol(symbol="ZZZZ")
        assert len(items) == 0

    async def test_by_symbol_sorted_by_score(self, seeded_session):
        svc = RecommendationService(seeded_session)
        items = await svc.get_recommendations_by_symbol(symbol="AAPL")
        scores = [r.score for r in items if r.score is not None]
        assert scores == sorted(scores, reverse=True)


# ── Count ──

@pytest.mark.asyncio
class TestCount:
    async def test_count_all(self, seeded_session):
        svc = RecommendationService(seeded_session)
        assert await svc.count_recommendations() == 4

    async def test_count_by_symbol(self, seeded_session):
        svc = RecommendationService(seeded_session)
        assert await svc.count_recommendations(symbol="AAPL") == 2

    async def test_count_by_direction(self, seeded_session):
        svc = RecommendationService(seeded_session)
        assert await svc.count_recommendations(direction="buy") == 2

    async def test_count_by_status(self, seeded_session):
        svc = RecommendationService(seeded_session)
        assert await svc.count_recommendations(status="active") == 4


# ── Decision ──

@pytest.mark.asyncio
class TestDecision:
    async def test_set_decision_acted(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="AAPL", direction="buy")
        updated = await svc.set_decision(
            rec.id, decision="acted", decision_reason="Strong technical setup",
        )
        assert updated is not None
        assert updated.decision == "acted"
        assert updated.decision_reason == "Strong technical setup"
        assert updated.decided_at is not None

    async def test_set_decision_ignored(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="AAPL", direction="buy")
        updated = await svc.set_decision(rec.id, decision="ignored")
        assert updated.decision == "ignored"
        assert updated.decided_at is not None

    async def test_set_decision_not_found(self, session):
        svc = RecommendationService(session)
        assert await svc.set_decision(9999, decision="acted") is None

    async def test_set_decision_default_reason(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="AAPL", direction="buy")
        updated = await svc.set_decision(rec.id, decision="acted")
        assert updated.decision_reason is None


# ── Outcome ──

@pytest.mark.asyncio
class TestOutcome:
    async def test_set_outcome_correct(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="AAPL", direction="buy")
        updated = await svc.set_outcome(
            rec.id, outcome="correct", actual_outcome_pnl=500.0,
            outcome_details='{"exit_price": 255.0, "hold_days": 14}',
        )
        assert updated is not None
        assert updated.outcome == "correct"
        assert updated.actual_outcome_pnl == 500.0
        assert updated.outcome_details == '{"exit_price": 255.0, "hold_days": 14}'
        assert updated.resolved_at is not None

    async def test_set_outcome_incorrect(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="TSLA", direction="buy")
        updated = await svc.set_outcome(
            rec.id, outcome="incorrect", actual_outcome_pnl=-300.0,
        )
        assert updated.outcome == "incorrect"
        assert updated.actual_outcome_pnl == -300.0
        assert updated.resolved_at is not None

    async def test_set_outcome_not_found(self, session):
        svc = RecommendationService(session)
        assert await svc.set_outcome(9999, outcome="correct") is None

    async def test_set_outcome_partial(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="AAPL", direction="buy")
        updated = await svc.set_outcome(rec.id, outcome="pending")
        assert updated.outcome == "pending"
        assert updated.actual_outcome_pnl is None
        assert updated.outcome_details is None
        assert updated.resolved_at is not None


# ── Update Status ──

@pytest.mark.asyncio
class TestUpdate:
    async def test_update_status(self, session):
        svc = RecommendationService(session)
        rec = await svc.create_recommendation(symbol="TEST", direction="buy")
        updated = await svc.update_status(rec.id, "expired")
        assert updated is not None
        assert updated.status == "expired"

    async def test_update_status_not_found(self, session):
        svc = RecommendationService(session)
        assert await svc.update_status(9999, "expired") is None
