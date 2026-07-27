from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.sector import SectorPerformance
from titan_x.models.market_breadth import MarketBreadth
from titan_x.services.market_heatmap_service import MarketHeatmapService

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
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=35)

    for sym, sector, industry, price_now, price_before in [
        ("AAPL", "Technology", "Hardware", 200.0, 180.0),
        ("MSFT", "Technology", "Software", 350.0, 320.0),
        ("GOOG", "Technology", "Software", 150.0, 140.0),
        ("NVDA", "Technology", "Hardware", 800.0, 750.0),
        ("JPM", "Financials", "Banking", 180.0, 175.0),
        ("GS", "Financials", "Banking", 450.0, 430.0),
        ("BAC", "Financials", "Banking", 40.0, 42.0),
        ("PG", "Consumer", "Staples", 160.0, 155.0),
        ("KO", "Consumer", "Staples", 65.0, 60.0),
        ("XOM", "Energy", "Oil", 120.0, 130.0),
        ("CVX", "Energy", "Oil", 145.0, 155.0),
        ("AMZN", "Technology", "E-Commerce", 180.0, 170.0),
    ]:
        session.add(Company(symbol=sym, company_name=sym, sector=sector, industry=industry, isin=f"US{sym}01", exchange="NYSE"))
        session.add(DailyPrice(symbol=sym, trade_date=week_ago, open=price_before, high=price_before, low=price_before, close=price_before, volume=1_000_000))
        session.add(DailyPrice(symbol=sym, trade_date=today, open=price_now, high=price_now, low=price_now, close=price_now, volume=2_000_000))

    session.add(SectorPerformance(sector="Technology", as_of_date=today, period_label="1M", return_pct=8.5, momentum_score=75.0, relative_strength=1.2, rank=1, constituent_count=5))
    session.add(SectorPerformance(sector="Financials", as_of_date=today, period_label="1M", return_pct=2.0, momentum_score=55.0, relative_strength=0.3, rank=3, constituent_count=3))
    session.add(SectorPerformance(sector="Consumer", as_of_date=today, period_label="1M", return_pct=5.0, momentum_score=65.0, relative_strength=0.8, rank=2, constituent_count=2))
    session.add(SectorPerformance(sector="Energy", as_of_date=today, period_label="1M", return_pct=-5.0, momentum_score=35.0, relative_strength=-1.0, rank=4, constituent_count=2))

    session.add(MarketBreadth(trade_date=today, advancing=8, declining=4, unchanged=0, total_stocks=12, advancing_volume=12_000_000, declining_volume=6_000_000, unchanged_volume=0, total_volume=18_000_000, new_highs=5, new_lows=2, advance_decline_ratio=2.0, breadth_oscillator=35.0, index_strength_score=68.0))

    await session.commit()
    return session


# ── Helper Tests ──

class TestHelpers:
    def test_period_days_import(self):
        from titan_x.services.market_heatmap_service import PERIOD_DAYS
        assert PERIOD_DAYS["1W"] == 7
        assert PERIOD_DAYS["1M"] == 30
        assert PERIOD_DAYS["3M"] == 90
        assert PERIOD_DAYS["YTD"] == 0

    @pytest.mark.asyncio
    async def test_get_sectors(self, session):
        session.add(Company(symbol="T1", company_name="T1", sector="Tech", isin="US001", exchange="NYSE"))
        session.add(Company(symbol="T2", company_name="T2", sector="Finance", isin="US002", exchange="NYSE"))
        await session.flush()
        svc = MarketHeatmapService(session)
        sectors = await svc._get_sectors()
        assert "Tech" in sectors
        assert "Finance" in sectors

    @pytest.mark.asyncio
    async def test_get_symbols_for_sector(self, session):
        session.add(Company(symbol="A", company_name="A", sector="Tech", isin="US001", exchange="NYSE"))
        session.add(Company(symbol="B", company_name="B", sector="Tech", isin="US002", exchange="NYSE"))
        session.add(Company(symbol="C", company_name="C", sector="Finance", isin="US003", exchange="NYSE"))
        await session.flush()
        svc = MarketHeatmapService(session)
        syms = await svc._get_symbols_for_sector("Tech")
        assert set(syms) == {"A", "B"}

    @pytest.mark.asyncio
    async def test_get_industries_for_sector(self, session):
        session.add(Company(symbol="A", company_name="A", sector="Tech", industry="Hardware", isin="US001", exchange="NYSE"))
        session.add(Company(symbol="B", company_name="B", sector="Tech", industry="Software", isin="US002", exchange="NYSE"))
        session.add(Company(symbol="C", company_name="C", sector="Tech", industry="Software", isin="US003", exchange="NYSE"))
        await session.flush()
        svc = MarketHeatmapService(session)
        inds = await svc._get_industries_for_sector("Tech")
        assert set(inds) == {"Hardware", "Software"}

    @pytest.mark.asyncio
    async def test_get_breadth_no_data(self, session):
        svc = MarketHeatmapService(session)
        b = await svc._get_breadth(date.today())
        assert b["advancing"] is None

    @pytest.mark.asyncio
    async def test_get_sector_performance_no_data(self, session):
        svc = MarketHeatmapService(session)
        p = await svc._get_sector_performance("NONE", date.today(), "1M")
        assert p == {}


# ── Heatmap Integration Tests ──

@pytest.mark.asyncio
class TestHeatmap:
    async def test_heatmap_returns_structure(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        assert "as_of_date" in result
        assert "period" in result
        assert "sectors" in result
        assert "leaders" in result
        assert "laggards" in result
        assert "breadth" in result
        assert "summary" in result
        assert result["period"] == "1M"

    async def test_heatmap_returns_all_sectors(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        sector_names = [s["name"] for s in result["sectors"]]
        assert "Technology" in sector_names
        assert "Financials" in sector_names
        assert "Consumer" in sector_names
        assert "Energy" in sector_names

    async def test_heatmap_sectors_ordered_by_return(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        returns = [s.get("return_pct") for s in result["sectors"] if s.get("return_pct") is not None]
        assert returns == sorted(returns, reverse=True)

    async def test_heatmap_sector_has_metrics(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        tech = next(s for s in result["sectors"] if s["name"] == "Technology")
        assert tech["return_pct"] is not None
        assert tech["momentum_score"] == 75.0
        assert tech["relative_strength"] == 1.2
        assert tech["rank"] == 1
        assert tech["constituent_count"] == 5
        assert tech["volume"] > 0

    async def test_heatmap_sector_has_industries(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        tech = next(s for s in result["sectors"] if s["name"] == "Technology")
        assert len(tech["industries"]) > 0
        ind_names = [i["name"] for i in tech["industries"]]
        assert "Hardware" in ind_names
        assert "Software" in ind_names

    async def test_heatmap_industry_has_metrics(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        tech = next(s for s in result["sectors"] if s["name"] == "Technology")
        hw = next(i for i in tech["industries"] if i["name"] == "Hardware")
        assert hw["constituent_count"] >= 2
        assert hw["return_pct"] is not None
        assert hw["volume"] > 0

    async def test_heatmap_leaders_and_laggards(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        assert len(result["leaders"]) > 0
        assert len(result["laggards"]) > 0
        for l in result["leaders"]:
            assert "symbol" in l
            assert "return_pct" in l
        for l in result["laggards"]:
            assert "symbol" in l
            assert "return_pct" in l

    async def test_breadth_included(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        b = result["breadth"]
        assert b["advancing"] == 8
        assert b["declining"] == 4
        assert b["total_stocks"] == 12
        assert b["advance_decline_ratio"] == 2.0
        assert b["index_strength_score"] == 68.0

    async def test_summary_included(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        s = result["summary"]
        assert s["total_sectors"] == 4
        assert s["advancing_sectors"] >= 2
        assert s["avg_sector_return_pct"] is not None
        assert s["total_volume"] > 0
        assert s["best_sector"] is not None
        assert s["worst_sector"] is not None

    async def test_different_period(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap(period="1W")
        assert result["period"] == "1W"

    async def test_custom_date(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        yesterday = date.today() - timedelta(days=1)
        session = seeded_session

        existing = (await session.execute(
            select(SectorPerformance).where(SectorPerformance.sector == "Technology")
        )).scalar_one_or_none()

        result = await svc.get_heatmap(as_of_date=yesterday)
        assert result["as_of_date"] == yesterday.isoformat()

    async def test_leaders_outperform_laggards(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        leader_returns = [l["return_pct"] for l in result["leaders"] if l["return_pct"] is not None]
        laggard_returns = [l["return_pct"] for l in result["laggards"] if l["return_pct"] is not None]
        if leader_returns and laggard_returns:
            assert sum(leader_returns) / len(leader_returns) >= sum(laggard_returns) / len(laggard_returns)


# ── Empty Data Tests ──

@pytest.mark.asyncio
class TestEmptyData:
    async def test_no_companies(self, session):
        svc = MarketHeatmapService(session)
        result = await svc.get_heatmap()
        assert result["sectors"] == []
        assert result["leaders"] == []
        assert result["laggards"] == []

    async def test_no_prices(self, session):
        session.add(Company(symbol="T1", company_name="T1", sector="Tech", isin="US001", exchange="NYSE"))
        await session.flush()
        svc = MarketHeatmapService(session)
        result = await svc.get_heatmap()
        assert len(result["sectors"]) == 1
        assert result["leaders"] == []
        assert result["laggards"] == []

    async def test_energy_is_laggard(self, seeded_session):
        svc = MarketHeatmapService(seeded_session)
        result = await svc.get_heatmap()
        energy = next(s for s in result["sectors"] if s["name"] == "Energy")
        assert energy["return_pct"] is not None and energy["return_pct"] < 0
        assert energy["relative_strength"] < 0



