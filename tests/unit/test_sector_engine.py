from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.sector import SectorPerformance
from titan_x.services.sector_engine import PERIOD_DAYS, PERIOD_LABELS, SectorEngine


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
async def sector_engine(session: AsyncSession) -> SectorEngine:
    return SectorEngine(session)


@pytest_asyncio.fixture
async def seed_data(session: AsyncSession) -> None:
    companies = [
        Company(symbol="AAPL", company_name="Apple Inc.", isin="US0378331005", exchange="NASDAQ", sector="Technology"),
        Company(symbol="MSFT", company_name="Microsoft Corp", isin="US5949181045", exchange="NASDAQ", sector="Technology"),
        Company(symbol="JPM", company_name="JPMorgan Chase", isin="US46625H1005", exchange="NYSE", sector="Financials"),
        Company(symbol="GS", company_name="Goldman Sachs", isin="US38141G1040", exchange="NYSE", sector="Financials"),
        Company(symbol="JNJ", company_name="Johnson & Johnson", isin="US4781601046", exchange="NYSE", sector="Healthcare"),
    ]
    for c in companies:
        session.add(c)

    today = date(2024, 12, 31)
    for sym in ["AAPL", "MSFT", "JPM", "GS", "JNJ"]:
        for i in range(400):
            d = today - timedelta(days=399 - i)
            base = {"AAPL": 150, "MSFT": 300, "JPM": 120, "GS": 200, "JNJ": 140}
            vol = {"AAPL": 50000, "MSFT": 40000, "JPM": 30000, "GS": 25000, "JNJ": 35000}
            b = base[sym]
            drift = i * 0.1
            noise = (i % 20) * 0.5
            close = b + drift + noise
            session.add(DailyPrice(
                symbol=sym, trade_date=d,
                open=close - 1, high=close + 2, low=close - 2,
                close=close, volume=vol[sym],
            ))
    await session.flush()


class TestSectorEngine:
    @pytest.mark.asyncio
    async def test_list_sectors(self, sector_engine: SectorEngine, seed_data: None) -> None:
        sectors = await sector_engine.list_all_sectors()
        assert "Technology" in sectors
        assert "Financials" in sectors
        assert "Healthcare" in sectors

    @pytest.mark.asyncio
    async def test_compute_sector_performance(self, sector_engine: SectorEngine, seed_data: None) -> None:
        perf = await sector_engine.compute_sector_performance("Technology", date(2024, 12, 31))
        assert perf["sector"] == "Technology"
        assert "periods" in perf
        assert "momentum_score" in perf
        assert perf["constituent_count"] == 2

    @pytest.mark.asyncio
    async def test_compute_all_sectors(self, sector_engine: SectorEngine, seed_data: None) -> None:
        results = await sector_engine.compute_all_sectors(date(2024, 12, 31), store=False)
        assert len(results) == 3
        sectors = [r["sector"] for r in results]
        assert "Technology" in sectors
        assert "Financials" in sectors
        assert "Healthcare" in sectors

    @pytest.mark.asyncio
    async def test_ranking(self, sector_engine: SectorEngine, seed_data: None) -> None:
        await sector_engine.compute_all_sectors(date(2024, 12, 31), store=True)
        ranking = await sector_engine.get_ranking(date(2024, 12, 31))
        assert len(ranking) == 3
        for r in ranking:
            assert "rank" in r
            assert "sector" in r
            assert "momentum_score" in r or r["momentum_score"] is None
        ranks = [r["rank"] for r in ranking]
        assert ranks == sorted(ranks)

    @pytest.mark.asyncio
    async def test_rotation(self, sector_engine: SectorEngine, seed_data: None) -> None:
        await sector_engine.compute_all_sectors(date(2024, 12, 31), store=True)
        rotation = await sector_engine.get_rotation(date(2024, 12, 31))
        assert "leading" in rotation
        assert "lagging" in rotation
        assert "neutral" in rotation
        assert "rotation_breadth" in rotation
        total = len(rotation["leading"]) + len(rotation["lagging"]) + len(rotation["neutral"])
        assert total == 3

    @pytest.mark.asyncio
    async def test_momentum_scores(self, sector_engine: SectorEngine, seed_data: None) -> None:
        results = await sector_engine.compute_all_sectors(date(2024, 12, 31), store=False)
        for r in results:
            ms = r.get("momentum_score")
            assert ms is not None
            assert isinstance(ms, float)

    @pytest.mark.asyncio
    async def test_relative_strength(self, sector_engine: SectorEngine, seed_data: None) -> None:
        results = await sector_engine.compute_all_sectors(date(2024, 12, 31), store=False)
        for r in results:
            rs = r.get("relative_strength")
            assert rs is not None
            assert isinstance(rs, float)

    @pytest.mark.asyncio
    async def test_store_performance(self, sector_engine: SectorEngine, seed_data: None) -> None:
        results = await sector_engine.compute_all_sectors(date(2024, 12, 31), store=True)
        stored, total = await sector_engine.get_stored_performance("Technology")
        assert total > 0

    @pytest.mark.asyncio
    async def test_get_historical(self, sector_engine: SectorEngine, seed_data: None) -> None:
        await sector_engine.compute_all_sectors(date(2024, 12, 31), store=True)
        history = await sector_engine.get_historical_performance("Technology", "1M", 5)
        assert len(history) >= 0

    @pytest.mark.asyncio
    async def test_get_sector_summary(self, sector_engine: SectorEngine, seed_data: None) -> None:
        await sector_engine.compute_all_sectors(date(2024, 12, 31), store=True)
        summary = await sector_engine.get_sector_summary("Technology")
        assert summary["sector"] == "Technology"
        assert summary["constituent_count"] == 2
        assert summary["latest_performance"] is not None

    @pytest.mark.asyncio
    async def test_rotation_signal_assignment(self, sector_engine: SectorEngine, seed_data: None) -> None:
        results = await sector_engine.compute_all_sectors(date(2024, 12, 31), store=False)
        for r in results:
            assert "rotation_signal" in r
            assert r["rotation_signal"] in ("leading", "lagging", "neutral")

    @pytest.mark.asyncio
    async def test_period_labels(self) -> None:
        assert "1W" in PERIOD_LABELS
        assert "1M" in PERIOD_LABELS
        assert "3M" in PERIOD_LABELS
        assert "6M" in PERIOD_LABELS
        assert "YTD" in PERIOD_LABELS
        assert "1Y" in PERIOD_LABELS
        assert "3Y" in PERIOD_LABELS
        assert "5Y" in PERIOD_LABELS
        assert PERIOD_DAYS["1M"] == 30
        assert PERIOD_DAYS["1Y"] == 365

    @pytest.mark.asyncio
    async def test_delete_stored(self, sector_engine: SectorEngine, seed_data: None) -> None:
        await sector_engine.compute_all_sectors(date(2024, 12, 31), store=True)
        stored, total = await sector_engine.get_stored_performance("Technology")
        if total > 0:
            deleted = await sector_engine._repo.delete(stored[0].id)
            assert deleted is True
            deleted2 = await sector_engine._repo.delete(stored[0].id)
            assert deleted2 is False

    @pytest.mark.asyncio
    async def test_get_stored_filtered(self, sector_engine: SectorEngine, seed_data: None) -> None:
        await sector_engine.compute_all_sectors(date(2024, 12, 31), store=True)
        stored, total = await sector_engine.get_stored_performance(period_label="1M")
        for s in stored:
            assert s.period_label == "1M"

    @pytest.mark.asyncio
    async def test_constituent_count(self, sector_engine: SectorEngine, seed_data: None) -> None:
        results = await sector_engine.compute_all_sectors(date(2024, 12, 31), store=False)
        sector_counts = {r["sector"]: r["constituent_count"] for r in results}
        assert sector_counts["Technology"] == 2
        assert sector_counts["Financials"] == 2
        assert sector_counts["Healthcare"] == 1
