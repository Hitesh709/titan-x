from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.price import CorporateAction
from titan_x.services.price_service import CorporateActionService


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
async def service(session: AsyncSession) -> CorporateActionService:
    return CorporateActionService(session)


class TestCorporateActionService:
    @pytest.mark.asyncio
    async def test_create_split(self, service: CorporateActionService) -> None:
        action = await service.create(
            symbol="RELIANCE", action_date=date(2024, 6, 1),
            action_type="split", ratio_numerator=1, ratio_denominator=10,
            adjustment_factor=0.1,
        )
        assert action.id is not None
        assert action.symbol == "RELIANCE"
        assert action.action_type == "split"
        assert action.adjustment_factor == 0.1

    @pytest.mark.asyncio
    async def test_create_dividend(self, service: CorporateActionService) -> None:
        action = await service.create(
            symbol="TCS", action_date=date(2024, 5, 15),
            action_type="dividend", dividend_amount=28.0,
        )
        assert action.dividend_amount == 28.0

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, service: CorporateActionService) -> None:
        await service.create(
            symbol="HDFC", action_date=date(2024, 3, 1),
            action_type="bonus", ratio_numerator=1, ratio_denominator=1,
        )
        with pytest.raises(ValueError, match="already exists"):
            await service.create(
                symbol="HDFC", action_date=date(2024, 3, 1),
                action_type="bonus",
            )

    @pytest.mark.asyncio
    async def test_list_for_symbol(self, service: CorporateActionService) -> None:
        await service.create(symbol="ITC", action_date=date(2024, 1, 1), action_type="dividend", dividend_amount=10.0)
        await service.create(symbol="ITC", action_date=date(2024, 6, 1), action_type="split", ratio_numerator=1, ratio_denominator=5, adjustment_factor=0.2)
        actions, total = await service.list_for_symbol("ITC")
        assert total == 2
        assert len(actions) == 2

    @pytest.mark.asyncio
    async def test_list_empty(self, service: CorporateActionService) -> None:
        actions, total = await service.list_for_symbol("UNKNOWN")
        assert total == 0
        assert len(actions) == 0

    @pytest.mark.asyncio
    async def test_delete(self, service: CorporateActionService) -> None:
        action = await service.create(symbol="DEL", action_date=date(2024, 1, 1), action_type="other")
        assert await service.delete(action.id) is True
        assert await service.delete(action.id) is False
