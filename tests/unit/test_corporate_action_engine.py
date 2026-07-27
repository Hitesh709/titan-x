from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.price import CorporateAction, DailyPrice
from titan_x.services.corporate_action_engine import AdjustmentEngine, CorporateActionEngine


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
async def engine(session: AsyncSession) -> CorporateActionEngine:
    return CorporateActionEngine(session)


@pytest_asyncio.fixture
async def seed_prices(session: AsyncSession) -> None:
    prices = [
        DailyPrice(symbol="RELIANCE", trade_date=date(2024, 5, 20), open=2500.0, high=2550.0, low=2480.0, close=2520.0, volume=1000000),
        DailyPrice(symbol="RELIANCE", trade_date=date(2024, 5, 21), open=2530.0, high=2560.0, low=2510.0, close=2540.0, volume=1100000),
        DailyPrice(symbol="RELIANCE", trade_date=date(2024, 5, 22), open=2550.0, high=2580.0, low=2520.0, close=2560.0, volume=900000),
        DailyPrice(symbol="RELIANCE", trade_date=date(2024, 6, 1), open=2600.0, high=2650.0, low=2580.0, close=2620.0, volume=1200000),
    ]
    for p in prices:
        session.add(p)
    await session.flush()


class TestAdjustmentEngine:
    def test_split_factor(self) -> None:
        assert AdjustmentEngine.split_factor(1, 10) == pytest.approx(10.0)
        assert AdjustmentEngine.split_factor(1, 2) == pytest.approx(2.0)

    def test_split_factor_invalid(self) -> None:
        with pytest.raises(ValueError):
            AdjustmentEngine.split_factor(0, 10)

    def test_bonus_factor(self) -> None:
        assert AdjustmentEngine.bonus_factor(1, 1) == pytest.approx(0.5)
        assert AdjustmentEngine.bonus_factor(1, 4) == pytest.approx(0.8)

    def test_rights_factor(self) -> None:
        factor = AdjustmentEngine.rights_factor(1, 4, 100, 80)
        expected = (4 * 100 + 1 * 80) / 5 / 100
        assert factor == pytest.approx(expected)

    def test_dividend_factor(self) -> None:
        assert AdjustmentEngine.dividend_factor(100, 5) == pytest.approx(0.95)
        assert AdjustmentEngine.dividend_factor(100, 0) == pytest.approx(1.0)

    def test_dividend_factor_invalid(self) -> None:
        with pytest.raises(ValueError):
            AdjustmentEngine.dividend_factor(0, 5)

    def test_merger_factor(self) -> None:
        assert AdjustmentEngine.merger_factor(1, 2) == pytest.approx(2.0)

    def test_acquisition_factor(self) -> None:
        assert AdjustmentEngine.acquisition_factor(1, 1) == pytest.approx(1.0)


class TestCorporateActionEngine:
    @pytest.mark.asyncio
    async def test_record_split(self, engine: CorporateActionEngine) -> None:
        action = await engine.record_split("RELIANCE", date(2024, 6, 1), 1, 10)
        assert action.symbol == "RELIANCE"
        assert action.action_type == "split"
        assert action.adjustment_factor == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_record_bonus(self, engine: CorporateActionEngine) -> None:
        action = await engine.record_bonus("HDFC", date(2024, 3, 1), 1, 1)
        assert action.action_type == "bonus"
        assert action.adjustment_factor == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_record_dividend(self, engine: CorporateActionEngine, session: AsyncSession) -> None:
        session.add(DailyPrice(symbol="TCS", trade_date=date(2024, 5, 14), open=100, high=110, low=95, close=100, volume=100))
        await session.flush()
        action = await engine.record_dividend("TCS", date(2024, 5, 15), 28.0)
        assert action.action_type == "dividend"
        assert action.dividend_amount == 28.0

    @pytest.mark.asyncio
    async def test_record_rights(self, engine: CorporateActionEngine) -> None:
        action = await engine.record_rights("ITC", date(2024, 4, 1), 1, 4, 100, 80)
        assert action.action_type == "rights"
        assert action.rights_premium == 100
        assert action.rights_issue_price == 80

    @pytest.mark.asyncio
    async def test_record_merger(self, engine: CorporateActionEngine) -> None:
        action = await engine.record_merger("OLDCO", date(2024, 7, 1), 1, 2, "NEWCO")
        assert action.action_type == "merger"
        assert action.new_symbol == "NEWCO"

    @pytest.mark.asyncio
    async def test_record_acquisition(self, engine: CorporateActionEngine) -> None:
        action = await engine.record_acquisition("BUYER", date(2024, 8, 1), 1, 1, "TARGET")
        assert action.action_type == "acquisition"
        assert action.old_symbol == "TARGET"

    @pytest.mark.asyncio
    async def test_duplicate_raises(self, engine: CorporateActionEngine) -> None:
        await engine.record_split("RELIANCE", date(2024, 6, 1), 1, 10)
        with pytest.raises(ValueError, match="already recorded"):
            await engine.record_split("RELIANCE", date(2024, 6, 1), 1, 5)

    @pytest.mark.asyncio
    async def test_list_actions(self, engine: CorporateActionEngine) -> None:
        await engine.record_split("ITC", date(2024, 6, 1), 1, 5)
        await engine.record_dividend("ITC", date(2024, 1, 1), 10.0)
        actions, total = await engine.list_actions("ITC")
        assert total == 2
        assert len(actions) == 2

    @pytest.mark.asyncio
    async def test_list_actions_empty(self, engine: CorporateActionEngine) -> None:
        actions, total = await engine.list_actions("UNKNOWN")
        assert total == 0
        assert len(actions) == 0

    @pytest.mark.asyncio
    async def test_list_all_by_type(self, engine: CorporateActionEngine) -> None:
        await engine.record_split("A", date(2024, 1, 1), 1, 2)
        await engine.record_split("B", date(2024, 2, 1), 1, 5)
        await engine.record_dividend("C", date(2024, 3, 1), 1.0)
        splits, total = await engine.list_all_by_type("split")
        assert total == 2
        assert len(splits) == 2
        dividends, total_d = await engine.list_all_by_type("dividend")
        assert total_d == 1

    @pytest.mark.asyncio
    async def test_get_action(self, engine: CorporateActionEngine) -> None:
        action = await engine.record_split("RELIANCE", date(2024, 6, 1), 1, 10)
        fetched = await engine.get_action(action.id)
        assert fetched is not None
        assert fetched.id == action.id

    @pytest.mark.asyncio
    async def test_get_action_not_found(self, engine: CorporateActionEngine) -> None:
        assert await engine.get_action(9999) is None

    @pytest.mark.asyncio
    async def test_delete_action(self, engine: CorporateActionEngine) -> None:
        action = await engine.record_split("DEL", date(2024, 1, 1), 1, 2)
        assert await engine.delete_action(action.id) is True
        assert await engine.delete_action(action.id) is False

    @pytest.mark.asyncio
    async def test_adjust_prices_split(self, engine: CorporateActionEngine, seed_prices: None) -> None:
        await engine.record_split("RELIANCE", date(2024, 6, 1), 1, 10)
        result = await engine.adjust_prices("RELIANCE")
        assert result["symbol"] == "RELIANCE"
        assert result["actions_used"] == 1
        assert result["prices_adjusted"] == 4

    @pytest.mark.asyncio
    async def test_adjust_prices_no_actions(self, engine: CorporateActionEngine, seed_prices: None) -> None:
        result = await engine.adjust_prices("RELIANCE")
        assert result["actions_used"] == 0
        assert result["prices_adjusted"] == 4

    @pytest.mark.asyncio
    async def test_adjust_prices_no_prices(self, engine: CorporateActionEngine) -> None:
        await engine.record_split("NODATA", date(2024, 6, 1), 1, 10)
        result = await engine.adjust_prices("NODATA")
        assert result["prices_adjusted"] == 0
