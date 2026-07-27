from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.news import NewsArticle
from titan_x.models.professional_report import ProfessionalReport
from titan_x.models.sector import SectorPerformance
from titan_x.models.strategy import Strategy
from titan_x.models.user import User
from titan_x.services.global_search_service import GlobalSearchService

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
async def user(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        u = User(email="search@test.com", hashed_password="pw")
        s.add(u)
        await s.commit()
        yield u
        await s.close()


@pytest_asyncio.fixture
async def session(engine, user):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def seeded_session(session, user):
    session.add_all([
        Company(symbol="AAPL", company_name="Apple Inc", isin="US0378331005", sector="Technology", industry="Consumer Electronics", exchange="NASDAQ", description="iPhone maker"),
        Company(symbol="MSFT", company_name="Microsoft Corp", isin="US5949181045", sector="Technology", industry="Software", exchange="NASDAQ", description="Windows maker"),
        Company(symbol="TSLA", company_name="Tesla Inc", isin="US88160R1014", sector="Automotive", industry="Electric Vehicles", exchange="NASDAQ"),
        SectorPerformance(sector="Technology", as_of_date=date.today(), period_label="1D", return_pct=1.5, momentum_score=0.8),
        SectorPerformance(sector="Automotive", as_of_date=date.today(), period_label="1D", return_pct=-0.5, momentum_score=0.3),
            ProfessionalReport(symbol="AAPL", trade_date=date.today(), direction="bullish", current_price=200.0, html_content="<html></html>"),
        Strategy(user_id=user.id, name="Momentum Breakout", description="Buy breakouts with volume confirmation"),
        Strategy(user_id=user.id, name="Mean Reversion", description="Sell rips buy dips"),
    ])
    await session.commit()
    yield session


class TestSearchBase:
    CATEGORIES = ["companies", "symbols", "sectors", "reports", "strategies", "news"]


@pytest.mark.asyncio
class TestEmptyQuery(TestSearchBase):
    async def test_empty_string(self, session, user):
        svc = GlobalSearchService(session)
        result = await svc.search("", user.id)
        for cat in self.CATEGORIES:
            assert result[cat] == []
        assert result["total_results"] == 0

    async def test_whitespace(self, session, user):
        svc = GlobalSearchService(session)
        result = await svc.search("   ", user.id)
        for cat in self.CATEGORIES:
            assert result[cat] == []


@pytest.mark.asyncio
class TestCompanies(TestSearchBase):
    async def test_search_by_name(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Apple", user.id)
        assert len(result["companies"]) == 1
        assert result["companies"][0]["symbol"] == "AAPL"
        assert result["companies"][0]["company_name"] == "Apple Inc"

    async def test_search_by_sector(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Technology", user.id)
        assert len(result["companies"]) >= 2

    async def test_search_by_industry(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Software", user.id)
        assert len(result["companies"]) == 1
        assert result["companies"][0]["symbol"] == "MSFT"

    async def test_search_by_description(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("iPhone", user.id)
        assert len(result["companies"]) == 1
        assert result["companies"][0]["symbol"] == "AAPL"

    async def test_no_match(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("NonExistentCo", user.id)
        companies = result["companies"]
        assert len(companies) == 0


@pytest.mark.asyncio
class TestSymbols(TestSearchBase):
    async def test_search_by_symbol_exact(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("AAPL", user.id)
        assert len(result["symbols"]) == 1
        assert result["symbols"][0]["symbol"] == "AAPL"
        assert result["symbols"][0]["company_name"] == "Apple Inc"

    async def test_search_by_symbol_partial(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("MS", user.id)
        assert len(result["symbols"]) == 1
        assert result["symbols"][0]["symbol"] == "MSFT"

    async def test_symbol_no_match(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("ZZZZ", user.id)
        assert len(result["symbols"]) == 0


@pytest.mark.asyncio
class TestSectors(TestSearchBase):
    async def test_search_sector_name(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Technology", user.id)
        assert len(result["sectors"]) == 1
        assert result["sectors"][0]["sector"] == "Technology"
        assert result["sectors"][0]["latest_return_pct"] == 1.5

    async def test_search_sector_partial(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Auto", user.id)
        assert len(result["sectors"]) == 1
        assert result["sectors"][0]["sector"] == "Automotive"

    async def test_no_match(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Healthcare", user.id)
        assert len(result["sectors"]) == 0


@pytest.mark.asyncio
class TestReports(TestSearchBase):
    async def test_search_by_symbol(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("AAPL", user.id)
        assert len(result["reports"]) == 1
        assert result["reports"][0]["direction"] == "bullish"

    async def test_search_by_direction(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("bullish", user.id)
        assert len(result["reports"]) == 1


@pytest.mark.asyncio
class TestStrategies(TestSearchBase):
    async def test_search_by_name(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Momentum", user.id)
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["name"] == "Momentum Breakout"

    async def test_search_by_description(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("dips", user.id)
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["name"] == "Mean Reversion"

    async def test_other_user_strategy_not_found(self, seeded_session, user):
        other = User(email="other@test.com", hashed_password="pw")
        seeded_session.add(other)
        await seeded_session.flush()
        seeded_session.add(Strategy(user_id=other.id, name="Hidden Strategy"))
        await seeded_session.commit()
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Hidden", user.id)
        assert len(result["strategies"]) == 0


@pytest.mark.asyncio
class TestNews(TestSearchBase):
    async def test_search_by_title(self, seeded_session, user):
        now = datetime.now(timezone.utc)
        seeded_session.add(NewsArticle(
            title="Apple reports record earnings", symbol="AAPL",
            source="Reuters", source_id="r1", url="http://test.com/n1", url_hash="hn1",
            published_at=now,
        ))
        await seeded_session.commit()
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("record earnings", user.id)
        assert len(result["news"]) == 1
        assert result["news"][0]["symbol"] == "AAPL"

    async def test_search_by_symbol(self, seeded_session, user):
        now = datetime.now(timezone.utc)
        seeded_session.add(NewsArticle(
            title="Tesla delivery numbers", symbol="TSLA",
            source="Bloomberg", source_id="r2", url="http://test.com/n2", url_hash="hn2",
            published_at=now,
        ))
        await seeded_session.commit()
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("TSLA", user.id)
        assert len(result["news"]) == 1


@pytest.mark.asyncio
class TestCombined(TestSearchBase):
    async def test_matches_multiple_categories(self, seeded_session, user):
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("AAPL", user.id)
        assert len(result["companies"]) >= 1
        assert len(result["symbols"]) >= 1
        assert len(result["reports"]) >= 1
        assert result["total_results"] >= 3

    async def test_limit_per_category(self, seeded_session, user):
        for i in range(20):
            seeded_session.add(
                Company(symbol=f"TST{i}", company_name=f"Test Company {i}", isin=f"US{i:09d}", sector="Test", exchange="NYSE")
            )
        await seeded_session.commit()
        svc = GlobalSearchService(seeded_session)
        result = await svc.search("Test", user.id, limit=5)
        assert len(result["companies"]) <= 5
