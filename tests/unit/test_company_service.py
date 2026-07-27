from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.services.company_service import CompanyService


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
async def service(session: AsyncSession) -> CompanyService:
    return CompanyService(session)


class TestCompanyService:
    @pytest.mark.asyncio
    async def test_create_company(self, service: CompanyService) -> None:
        company = await service.create(
            symbol="RELIANCE",
            company_name="Reliance Industries Ltd",
            isin="INE002A01018",
            exchange="NSE",
            sector="Conglomerate",
            industry="Diversified",
            market_cap=17_000_000_000_000,
            listing_date=date(2000, 1, 1),
        )
        assert company.id is not None
        assert company.symbol == "RELIANCE"
        assert company.isin == "INE002A01018"
        assert company.exchange == "NSE"

    @pytest.mark.asyncio
    async def test_create_duplicate_symbol_raises(self, service: CompanyService) -> None:
        await service.create(symbol="TCS", company_name="Tata Consultancy Services", isin="INE467B01029", exchange="NSE")
        with pytest.raises(ValueError, match="symbol or ISIN already exists"):
            await service.create(symbol="TCS", company_name="Duplicate", isin="INE467B01030", exchange="BSE")

    @pytest.mark.asyncio
    async def test_create_duplicate_isin_raises(self, service: CompanyService) -> None:
        await service.create(symbol="HDFC", company_name="HDFC Bank", isin="INE040A01034", exchange="NSE")
        with pytest.raises(ValueError, match="symbol or ISIN already exists"):
            await service.create(symbol="HDFCB", company_name="HDFC Duplicate", isin="INE040A01034", exchange="BSE")

    @pytest.mark.asyncio
    async def test_get_by_id(self, service: CompanyService) -> None:
        created = await service.create(symbol="INFY", company_name="Infosys Ltd", isin="INE009A01021", exchange="NSE")
        found = await service.get_by_id(created.id)
        assert found is not None
        assert found.symbol == "INFY"

    @pytest.mark.asyncio
    async def test_get_by_id_missing(self, service: CompanyService) -> None:
        assert await service.get_by_id(999) is None

    @pytest.mark.asyncio
    async def test_get_by_symbol(self, service: CompanyService) -> None:
        await service.create(symbol="WIPRO", company_name="Wipro Ltd", isin="INE075A01022", exchange="NSE")
        found = await service.get_by_symbol("WIPRO")
        assert found is not None
        assert found.company_name == "Wipro Ltd"

    @pytest.mark.asyncio
    async def test_get_by_symbol_case_insensitive(self, service: CompanyService) -> None:
        await service.create(symbol="WIPRO", company_name="Wipro Ltd", isin="INE075A01022", exchange="NSE")
        found = await service.get_by_symbol("wipro")
        assert found is not None

    @pytest.mark.asyncio
    async def test_get_by_isin(self, service: CompanyService) -> None:
        await service.create(symbol="ITC", company_name="ITC Ltd", isin="INE154A01025", exchange="NSE")
        found = await service.get_by_isin("INE154A01025")
        assert found is not None
        assert found.symbol == "ITC"

    @pytest.mark.asyncio
    async def test_list_pagination(self, service: CompanyService) -> None:
        for i in range(10):
            await service.create(
                symbol=f"SYM{i:03d}", company_name=f"Company {i}",
                isin=f"INE{i:05d}A01025", exchange="NSE",
            )
        companies, total = await service.list(skip=0, limit=3)
        assert len(companies) == 3
        assert total == 10

    @pytest.mark.asyncio
    async def test_list_search_by_symbol(self, service: CompanyService) -> None:
        await service.create(symbol="TITAN", company_name="Titan Company Ltd", isin="INE280A01028", exchange="NSE")
        await service.create(symbol="TATASTEEL", company_name="Tata Steel Ltd", isin="INE081A01020", exchange="NSE")
        companies, total = await service.list(search="TITAN")
        assert total == 1
        assert companies[0].symbol == "TITAN"

    @pytest.mark.asyncio
    async def test_list_search_by_name(self, service: CompanyService) -> None:
        await service.create(symbol="BAJFINANCE", company_name="Bajaj Finance Ltd", isin="INE296A01024", exchange="NSE")
        companies, total = await service.list(search="Bajaj")
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_filter_by_exchange(self, service: CompanyService) -> None:
        await service.create(symbol="NSE1", company_name="NSE Co", isin="INE000A01011", exchange="NSE")
        await service.create(symbol="BSE1", company_name="BSE Co", isin="INE000A01012", exchange="BSE")
        companies, total = await service.list(exchange="BSE")
        assert total == 1
        assert companies[0].exchange == "BSE"

    @pytest.mark.asyncio
    async def test_list_filter_by_sector(self, service: CompanyService) -> None:
        await service.create(symbol="IT1", company_name="IT Co", isin="INE000A01013", exchange="NSE", sector="Technology")
        await service.create(symbol="FIN1", company_name="Finance Co", isin="INE000A01014", exchange="NSE", sector="Finance")
        companies, total = await service.list(sector="Technology")
        assert total == 1

    @pytest.mark.asyncio
    async def test_update_company(self, service: CompanyService) -> None:
        company = await service.create(symbol="MARUTI", company_name="Maruti Suzuki India Ltd", isin="INE585B01010", exchange="NSE")
        updated = await service.update(company.id, sector="Automobile", market_cap=3_000_000_000_000)
        assert updated is not None
        assert updated.sector == "Automobile"
        assert updated.market_cap == 3_000_000_000_000

    @pytest.mark.asyncio
    async def test_update_missing_company(self, service: CompanyService) -> None:
        assert await service.update(999, company_name="Ghost") is None

    @pytest.mark.asyncio
    async def test_delete_company(self, service: CompanyService) -> None:
        company = await service.create(symbol="DEL", company_name="Delete Co", isin="INE000A01015", exchange="NSE")
        assert await service.delete(company.id) is True
        assert await service.get_by_id(company.id) is None

    @pytest.mark.asyncio
    async def test_delete_missing(self, service: CompanyService) -> None:
        assert await service.delete(999) is False

    @pytest.mark.asyncio
    async def test_list_sectors(self, service: CompanyService) -> None:
        await service.create(symbol="A", company_name="A", isin="INE000A01001", exchange="NSE", sector="Tech")
        await service.create(symbol="B", company_name="B", isin="INE000A01002", exchange="NSE", sector="Finance")
        await service.create(symbol="C", company_name="C", isin="INE000A01003", exchange="NSE", sector="Tech")
        sectors = await service.list_sectors()
        assert sorted(sectors) == sorted(["Tech", "Finance"])

    @pytest.mark.asyncio
    async def test_list_exchanges(self, service: CompanyService) -> None:
        await service.create(symbol="N", company_name="N", isin="INE000A01004", exchange="NSE")
        await service.create(symbol="B", company_name="B", isin="INE000A01005", exchange="BSE")
        exchanges = await service.list_exchanges()
        assert sorted(exchanges) == sorted(["NSE", "BSE"])
