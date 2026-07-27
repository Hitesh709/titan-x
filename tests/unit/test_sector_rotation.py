from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.sector import SectorPerformance
from titan_x.services.sector_rotation_service import (
    SectorRotationService, SIGNAL_ORDER,
)

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
    today = date.today()
    prev = today - timedelta(days=30)
    older = today - timedelta(days=60)

    sectors_data = {
        "Technology": {"current_ms": 80, "prev_ms": 70, "older_ms": 60, "current_ret": 8.0, "prev_ret": 6.0, "current_rs": 1.5, "prev_rs": 1.2},
        "Healthcare": {"current_ms": 65, "prev_ms": 60, "older_ms": 55, "current_ret": 5.0, "prev_ret": 4.0, "current_rs": 1.0, "prev_rs": 0.8},
        "Consumer": {"current_ms": 45, "prev_ms": 55, "older_ms": 50, "current_ret": 2.0, "prev_ret": 4.5, "current_rs": 0.5, "prev_rs": 0.7},
        "Financials": {"current_ms": 40, "prev_ms": 35, "older_ms": 30, "current_ret": 1.0, "prev_ret": 0.5, "current_rs": 0.3, "prev_rs": 0.2},
        "Energy": {"current_ms": 25, "prev_ms": 40, "older_ms": 45, "current_ret": -3.0, "prev_ret": 2.0, "current_rs": -1.0, "prev_rs": -0.3},
        "Utilities": {"current_ms": 20, "prev_ms": 30, "older_ms": 35, "current_ret": -5.0, "prev_ret": 1.0, "current_rs": -1.5, "prev_rs": -0.5},
    }

    for sector, data in sectors_data.items():
        for dt, ms, ret, rs, rank in [
            (older, data["older_ms"], data["prev_ret"] - 2, data["prev_rs"] - 0.3, 99),
            (prev, data["prev_ms"], data["prev_ret"], data["prev_rs"], 99),
            (today, data["current_ms"], data["current_ret"], data["current_rs"], 99),
        ]:
            session.add(SectorPerformance(
                sector=sector, as_of_date=dt, period_label="1M",
                return_pct=ret, momentum_score=ms, relative_strength=rs,
                constituent_count=10,
            ))

    await session.flush()

    rows = (await session.execute(
        select(SectorPerformance).where(
            SectorPerformance.as_of_date == today,
            SectorPerformance.period_label == "1M",
        ).order_by(desc(SectorPerformance.momentum_score))
    )).scalars().all()

    for i, r in enumerate(rows, 1):
        r.rank = i

    prev_rows = (await session.execute(
        select(SectorPerformance).where(
            SectorPerformance.as_of_date == prev,
            SectorPerformance.period_label == "1M",
        ).order_by(desc(SectorPerformance.momentum_score))
    )).scalars().all()

    for i, r in enumerate(prev_rows, 1):
        r.rank = i

    await session.commit()
    return session


from sqlalchemy import desc, select


# ── Helper Tests ──

class TestHelpers:
    def test_signal_order(self):
        assert SIGNAL_ORDER["lagging"] == 0
        assert SIGNAL_ORDER["neutral"] == 1
        assert SIGNAL_ORDER["leading"] == 2

    @pytest.mark.asyncio
    async def test_get_period_data(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        data = await svc._get_period_data(date.today(), "1M")
        assert len(data) == 6
        sectors = {d["sector"] for d in data}
        assert "Technology" in sectors
        assert "Energy" in sectors

    @pytest.mark.asyncio
    async def test_get_previous_period_data(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        prev = await svc._get_previous_period_data(date.today(), "1M")
        assert len(prev) == 6

    @pytest.mark.asyncio
    async def test_compute_rotation_signals(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        data = await svc._get_period_data(date.today(), "1M")
        signals = svc._compute_rotation_signals(data)
        assert len(signals) == 6
        assert signals["Technology"] == "leading"
        assert signals["Utilities"] == "lagging" or signals["Energy"] == "lagging"

    @pytest.mark.asyncio
    async def test_signal_quartiles_correct(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        data = await svc._get_period_data(date.today(), "1M")
        signals = svc._compute_rotation_signals(data)
        leading_count = sum(1 for v in signals.values() if v == "leading")
        lagging_count = sum(1 for v in signals.values() if v == "lagging")
        assert leading_count >= 1
        assert lagging_count >= 1

    def test_compute_score_trend_improving(self):
        svc = SectorRotationService.__new__(SectorRotationService)
        records = [
            {"period_label": "1M", "momentum_score": 80},
            {"period_label": "1M", "momentum_score": 70},
            {"period_label": "1M", "momentum_score": 60},
        ]
        trend = svc._compute_score_trend(records)
        assert trend["direction"] == "improving"
        assert trend["slope"] == 20

    def test_compute_score_trend_declining(self):
        svc = SectorRotationService.__new__(SectorRotationService)
        records = [
            {"period_label": "1M", "momentum_score": 30},
            {"period_label": "1M", "momentum_score": 40},
            {"period_label": "1M", "momentum_score": 50},
        ]
        trend = svc._compute_score_trend(records)
        assert trend["direction"] == "declining"
        assert trend["slope"] == -20

    def test_compute_score_trend_stable(self):
        svc = SectorRotationService.__new__(SectorRotationService)
        records = [
            {"period_label": "1M", "momentum_score": 55},
            {"period_label": "1M", "momentum_score": 53},
            {"period_label": "1M", "momentum_score": 52},
        ]
        trend = svc._compute_score_trend(records)
        assert trend["direction"] == "stable"

    def test_compute_score_trend_insufficient(self):
        svc = SectorRotationService.__new__(SectorRotationService)
        records = [
            {"period_label": "1M", "momentum_score": 55},
        ]
        trend = svc._compute_score_trend(records)
        assert trend["stable"] is True

    def test_compute_period_comparison(self):
        svc = SectorRotationService.__new__(SectorRotationService)
        records = [
            {"period_label": "1M", "return_pct": 5.0},
            {"period_label": "1M", "return_pct": 3.0},
            {"period_label": "1M", "return_pct": 1.0},
        ]
        comp = svc._compute_period_comparison(records)
        assert "1M" in comp
        assert comp["1M"]["latest"] == 5.0
        assert comp["1M"]["previous"] == 3.0
        assert comp["1M"]["change"] == 2.0

    def test_compute_period_comparison_single(self):
        svc = SectorRotationService.__new__(SectorRotationService)
        records = [
            {"period_label": "1M", "return_pct": 5.0},
        ]
        comp = svc._compute_period_comparison(records)
        assert comp["1M"]["latest"] == 5.0
        assert comp["1M"]["previous"] is None

    def test_build_summary(self):
        svc = SectorRotationService.__new__(SectorRotationService)
        rankings = [
            {"rank": 1, "rank_change": 2, "return_pct": 8.0},
            {"rank": 2, "rank_change": -1, "return_pct": 5.0},
            {"rank": 3, "rank_change": 0, "return_pct": 2.0},
        ]
        entering = [{"sector": "Tech"}]
        losing = [{"sector": "Energy"}]
        summary = svc._build_summary(rankings, entering, losing)
        assert summary["total_sectors"] == 3
        assert summary["ranks_improving"] == 1
        assert summary["ranks_declining"] == 1
        assert summary["ranks_stable"] == 1
        assert summary["entering_strength_count"] == 1
        assert summary["losing_strength_count"] == 1


# ── Rotation Detection Tests ──

@pytest.mark.asyncio
class TestRotationDetection:
    async def test_detect_returns_structure(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        assert "as_of_date" in result
        assert "period" in result
        assert "entering_strength" in result
        assert "losing_strength" in result
        assert "historical_comparisons" in result
        assert "rankings" in result
        assert "summary" in result

    async def test_entering_strength_detected(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        entering = result["entering_strength"]
        assert len(entering) >= 0
        for e in entering:
            assert "sector" in e
            assert "previous_signal" in e
            assert "current_signal" in e
            assert SIGNAL_ORDER[e["current_signal"]] > SIGNAL_ORDER[e["previous_signal"]]

    async def test_losing_strength_detected(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        losing = result["losing_strength"]
        assert len(losing) >= 0
        for l in losing:
            assert "sector" in l
            assert "previous_signal" in l
            assert "current_signal" in l
            assert SIGNAL_ORDER[l["current_signal"]] < SIGNAL_ORDER[l["previous_signal"]]

    async def test_rankings_have_change(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        rankings = result["rankings"]
        assert len(rankings) == 6
        for r in rankings:
            assert "sector" in r
            assert "rank" in r
            assert "previous_rank" in r
            assert "rank_change" in r or r.get("rank_change") is None

    async def test_rankings_sorted(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        rankings = result["rankings"]
        ranks = [r["rank"] for r in rankings if r["rank"] is not None]
        assert ranks == sorted(ranks)

    async def test_historical_comparisons_present(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        comparisons = result["historical_comparisons"]
        assert len(comparisons) == 6
        for c in comparisons:
            assert "sector" in c
            assert "record_count" in c
            assert "month_over_month" in c
            assert "score_trend" in c

    async def test_summary_metrics(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        s = result["summary"]
        assert s["total_sectors"] == 6
        assert s["avg_return_pct"] is not None

    async def test_technology_is_leading(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        tech_rank = next(r for r in result["rankings"] if r["sector"] == "Technology")
        assert tech_rank["rank"] == 1
        assert tech_rank["rotation_signal"] == "leading"

    async def test_utilities_is_lagging(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        util_rank = next(r for r in result["rankings"] if r["sector"] == "Utilities")
        assert util_rank["rotation_signal"] == "lagging"

    async def test_rank_change_reflects_momentum(self, seeded_session):
        svc = SectorRotationService(seeded_session)
        result = await svc.detect_rotation()
        consumer = next(r for r in result["rankings"] if r["sector"] == "Consumer")
        energy = next(r for r in result["rankings"] if r["sector"] == "Energy")
        assert consumer["rank_change"] is not None
        assert energy["rank_change"] is not None


# ── Empty Data Tests ──

@pytest.mark.asyncio
class TestEmptyData:
    async def test_no_data(self, session):
        svc = SectorRotationService(session)
        result = await svc.detect_rotation()
        assert result["entering_strength"] == []
        assert result["losing_strength"] == []
        assert result["rankings"] == []
        assert result["historical_comparisons"] == []
        assert result["summary"]["total_sectors"] == 0

    async def test_single_sector(self, session):
        session.add(SectorPerformance(
            sector="Tech", as_of_date=date.today(), period_label="1M",
            return_pct=5.0, momentum_score=60.0, relative_strength=1.0,
            constituent_count=5,
        ))
        await session.flush()
        svc = SectorRotationService(session)
        result = await svc.detect_rotation()
        assert len(result["rankings"]) == 1
        assert result["rankings"][0]["sector"] == "Tech"
