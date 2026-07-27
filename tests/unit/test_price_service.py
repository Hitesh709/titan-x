from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.price import DailyPrice
from titan_x.services.price_service import PriceService, PriceValidationError, validate_ohlcv


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
async def service(session: AsyncSession) -> PriceService:
    return PriceService(session)


class TestValidateOHLCV:
    def test_valid_data(self) -> None:
        errors = validate_ohlcv({"open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000})
        assert errors == []

    def test_high_below_low(self) -> None:
        errors = validate_ohlcv({"open": 100, "high": 95, "low": 99, "close": 102, "volume": 1000})
        assert "high must be >= low" in errors

    def test_open_outside_range(self) -> None:
        errors = validate_ohlcv({"open": 200, "high": 105, "low": 99, "close": 102, "volume": 1000})
        assert any("open" in e for e in errors)

    def test_close_outside_range(self) -> None:
        errors = validate_ohlcv({"open": 100, "high": 105, "low": 99, "close": 200, "volume": 1000})
        assert any("close" in e for e in errors)

    def test_negative_volume(self) -> None:
        errors = validate_ohlcv({"open": 100, "high": 105, "low": 99, "close": 102, "volume": -1})
        assert "volume must be non-negative" in errors

    def test_non_positive_prices(self) -> None:
        errors = validate_ohlcv({"open": 0, "high": 105, "low": 99, "close": 102, "volume": 1000})
        assert any("positive" in e for e in errors)


class TestPriceService:
    @pytest.mark.asyncio
    async def test_create_price(self, service: PriceService) -> None:
        p = await service.create_price("AAPL", date(2024, 1, 2), 180.0, 185.0, 179.0, 184.0, 50_000_000)
        assert p.id is not None
        assert p.symbol == "AAPL"
        assert p.trade_date == date(2024, 1, 2)

    @pytest.mark.asyncio
    async def test_create_price_invalid_raises(self, service: PriceService) -> None:
        with pytest.raises(PriceValidationError):
            await service.create_price("AAPL", date(2024, 1, 2), 200, 150, 140, 160, 1000)

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, service: PriceService) -> None:
        await service.create_price("AAPL", date(2024, 1, 2), 180, 185, 179, 184, 1000)
        with pytest.raises(ValueError, match="already exists"):
            await service.create_price("AAPL", date(2024, 1, 2), 181, 186, 178, 185, 1000)

    @pytest.mark.asyncio
    async def test_get_prices(self, service: PriceService) -> None:
        await service.create_price("AAPL", date(2024, 1, 2), 180, 185, 179, 184, 1000)
        await service.create_price("AAPL", date(2024, 1, 3), 184, 190, 183, 188, 1200)
        prices, total = await service.get_prices("AAPL")
        assert total == 2
        assert len(prices) == 2

    @pytest.mark.asyncio
    async def test_get_prices_date_range(self, service: PriceService) -> None:
        await service.create_price("AAPL", date(2024, 1, 2), 180, 185, 179, 184, 1000)
        await service.create_price("AAPL", date(2024, 1, 3), 184, 190, 183, 188, 1200)
        await service.create_price("AAPL", date(2024, 1, 4), 188, 192, 186, 190, 1100)
        prices, total = await service.get_prices("AAPL", start_date=date(2024, 1, 3))
        assert total == 2

    @pytest.mark.asyncio
    async def test_get_latest_price(self, service: PriceService) -> None:
        await service.create_price("AAPL", date(2024, 1, 2), 180, 185, 179, 184, 1000)
        await service.create_price("AAPL", date(2024, 1, 3), 184, 190, 183, 188, 1200)
        latest = await service.get_latest_price("AAPL")
        assert latest is not None
        assert latest.trade_date == date(2024, 1, 3)

    @pytest.mark.asyncio
    async def test_get_latest_price_empty(self, service: PriceService) -> None:
        assert await service.get_latest_price("UNKNOWN") is None

    @pytest.mark.asyncio
    async def test_delete_price(self, service: PriceService) -> None:
        p = await service.create_price("AAPL", date(2024, 1, 2), 180, 185, 179, 184, 1000)
        assert await service.delete_price(p.id) is True
        assert await service.delete_price(p.id) is False

    @pytest.mark.asyncio
    async def test_bulk_import(self, service: PriceService) -> None:
        records = [
            {"trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000},
            {"trade_date": "2024-01-03", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200},
        ]
        result = await service.bulk_import("AAPL", records)
        assert result.total == 2
        assert result.created == 2
        assert result.skipped_duplicates == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_bulk_import_deduplicates(self, service: PriceService) -> None:
        records = [
            {"trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000},
            {"trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000},
        ]
        result = await service.bulk_import("AAPL", records)
        assert result.created == 1
        assert result.skipped_duplicates == 1

    @pytest.mark.asyncio
    async def test_bulk_import_validation_errors(self, service: PriceService) -> None:
        records = [
            {"trade_date": "2024-01-02", "open": 200, "high": 150, "low": 179, "close": 184, "volume": 1000},
        ]
        result = await service.bulk_import("AAPL", records)
        assert result.created == 0
        assert len(result.errors) == 1
        assert "high must be >= low" in result.errors[0]["errors"]

    @pytest.mark.asyncio
    async def test_bulk_import_csv(self, service: PriceService) -> None:
        csv_content = "trade_date,open,high,low,close,volume\n2024-01-02,180,185,179,184,1000\n2024-01-03,184,190,183,188,1200\n"
        result = await service.bulk_import_csv("AAPL", csv_content)
        assert result.created == 2

    @pytest.mark.asyncio
    async def test_compute_adjusted_prices_no_actions(self, service: PriceService) -> None:
        await service.create_price("AAPL", date(2024, 1, 2), 180, 185, 179, 184, 1000)
        count = await service.compute_adjusted_prices("AAPL")
        assert count == 1
