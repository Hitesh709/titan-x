from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.infrastructure.market_data_providers import (
    AlphaVantageProvider,
    MockMarketDataProvider,
    NSEProvider,
    YahooFinanceProvider,
    get_market_data_provider,
)
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.user import User
from titan_x.services.market_data_service import MarketDataService


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
async def user(session: AsyncSession) -> User:
    u = User(email="market@test.com", hashed_password="hash")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> MarketDataService:
    return MarketDataService(session)


# ============================================================
# PROVIDER FACTORY
# ============================================================

class TestProviderFactory:
    def test_get_mock(self):
        p = get_market_data_provider("mock")
        assert isinstance(p, MockMarketDataProvider)

    def test_get_alphavantage(self):
        p = get_market_data_provider("alphavantage", api_key="test123")
        assert isinstance(p, AlphaVantageProvider)

    def test_get_yahoo(self):
        p = get_market_data_provider("yahoo")
        assert isinstance(p, YahooFinanceProvider)

    def test_get_nse(self):
        p = get_market_data_provider("nse")
        assert isinstance(p, NSEProvider)

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="Unsupported market data provider"):
            get_market_data_provider("nonexistent")


# ============================================================
# MOCK PROVIDER
# ============================================================

class TestMockProvider:
    @pytest.mark.asyncio
    async def test_get_historical_prices_defaults(self):
        provider = MockMarketDataProvider()
        points = await provider.get_historical_prices("RELIANCE")
        assert len(points) > 0
        for p in points:
            assert p.symbol == "RELIANCE"
            assert p.open > 0
            assert p.close > 0
            assert p.volume > 0

    @pytest.mark.asyncio
    async def test_get_historical_prices_date_range(self):
        provider = MockMarketDataProvider()
        start = date(2025, 1, 1)
        end = date(2025, 1, 31)
        points = await provider.get_historical_prices("TEST", start=start, end=end)
        assert len(points) > 0
        for p in points:
            assert start <= p.trade_date <= end

    @pytest.mark.asyncio
    async def test_get_quote(self):
        provider = MockMarketDataProvider()
        quote = await provider.get_quote("TCS")
        assert quote["symbol"] == "TCS"
        assert "last_price" in quote
        assert "change_percent" in quote

    @pytest.mark.asyncio
    async def test_get_company_profile(self):
        provider = MockMarketDataProvider()
        profile = await provider.get_company_profile("INFY")
        assert profile["symbol"] == "INFY"
        assert "name" in profile
        assert "sector" in profile


# ============================================================
# MARKET DATA SERVICE
# ============================================================

class TestMarketDataService:
    @pytest.mark.asyncio
    async def test_fetch_and_store(self, svc: MarketDataService):
        result = await svc.fetch_and_store_historical("RELIANCE", provider_name="mock")
        assert result["symbol"] == "RELIANCE"
        assert result["inserted"] > 0
        assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_fetch_and_store_creates_company(self, svc: MarketDataService, session: AsyncSession):
        await svc.fetch_and_store_historical("NEWCO", provider_name="mock")
        stmt = select(Company).where(Company.symbol == "NEWCO")
        result = await session.execute(stmt)
        company = result.scalar_one_or_none()
        assert company is not None
        assert company.company_name == "NEWCO Corp"

    @pytest.mark.asyncio
    async def test_fetch_and_store_skips_duplicates(self, svc: MarketDataService):
        r1 = await svc.fetch_and_store_historical("DUP", provider_name="mock")
        r2 = await svc.fetch_and_store_historical("DUP", provider_name="mock")
        assert r2["skipped"] > 0

    @pytest.mark.asyncio
    async def test_get_quote(self, svc: MarketDataService):
        quote = await svc.get_quote("RELIANCE", provider_name="mock")
        assert quote["symbol"] == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_company_profile(self, svc: MarketDataService, session: AsyncSession):
        profile = await svc.get_company_profile("TCS", provider_name="mock")
        assert profile["symbol"] == "TCS"
        stmt = select(Company).where(Company.symbol == "TCS")
        result = await session.execute(stmt)
        company = result.scalar_one_or_none()
        assert company is not None

    @pytest.mark.asyncio
    async def test_get_company_profile_existing(self, svc: MarketDataService, session: AsyncSession):
        c = Company(symbol="EXIST", company_name="Existing Corp", isin="INEXIST001", exchange="NSE")
        session.add(c)
        await session.flush()
        profile = await svc.get_company_profile("EXIST", provider_name="mock")
        assert profile["symbol"] == "EXIST"

    @pytest.mark.asyncio
    async def test_list_providers(self, svc: MarketDataService):
        providers = svc.get_available_providers()
        assert "mock" in providers
        assert "alphavantage" in providers
        assert "yahoo" in providers
        assert "nse" in providers

    @pytest.mark.asyncio
    async def test_invalid_provider_raises(self, svc: MarketDataService):
        with pytest.raises(ValueError, match="Unsupported market data provider"):
            await svc.fetch_and_store_historical("TEST", provider_name="invalid")
