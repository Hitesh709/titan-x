"""Tests for Trading Calendar service."""
from __future__ import annotations

from datetime import date, time

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from titan_x.db.base import Base
from titan_x.models.trading_calendar import (
    CorporateCalendar,
    ExpiryCalendar,
    SettlementCalendar,
    SpecialSession,
    TradingHoliday,
)
from titan_x.services.trading_calendar_service import TradingCalendarService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @event.listens_for(eng.sync_engine, "connect")
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
    SessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def service(session):
    return TradingCalendarService(session)


class TestTradingHolidays:
    async def test_add_holiday(self, service: TradingCalendarService):
        h = await service.add_holiday("NSE", date(2025, 1, 26), "Republic Day")
        assert h.exchange == "NSE"
        assert h.holiday_date == date(2025, 1, 26)
        assert h.description == "Republic Day"
        assert h.year == 2025
        assert h.is_recurring is False
        assert h.is_active is True

    async def test_add_holiday_duplicate(self, service: TradingCalendarService):
        h1 = await service.add_holiday("NSE", date(2025, 1, 26), "Republic Day")
        h2 = await service.add_holiday("NSE", date(2025, 1, 26), "Duplicate")
        assert h2.id == h1.id
        assert h2.description == "Republic Day"

    async def test_get_holiday(self, service: TradingCalendarService):
        h = await service.add_holiday("NSE", date(2025, 8, 15), "Independence Day")
        found = await service.get_holiday(h.id)
        assert found is not None
        assert found.id == h.id

    async def test_get_holiday_not_found(self, service: TradingCalendarService):
        assert await service.get_holiday(999) is None

    async def test_list_holidays(self, service: TradingCalendarService):
        await service.add_holiday("NSE", date(2025, 1, 26))
        await service.add_holiday("NSE", date(2025, 8, 15))
        await service.add_holiday("NYSE", date(2025, 1, 1))
        all_h = await service.list_holidays()
        assert len(all_h) == 3
        nse_h = await service.list_holidays(exchange="NSE")
        assert len(nse_h) == 2
        nyse_h = await service.list_holidays(exchange="NYSE")
        assert len(nyse_h) == 1

    async def test_list_holidays_by_year(self, service: TradingCalendarService):
        await service.add_holiday("NSE", date(2025, 1, 26))
        await service.add_holiday("NSE", date(2026, 1, 26))
        h2025 = await service.list_holidays(year=2025)
        assert len(h2025) == 1

    async def test_is_holiday(self, service: TradingCalendarService):
        await service.add_holiday("NSE", date(2025, 1, 26))
        assert await service.is_holiday("NSE", date(2025, 1, 26)) is True
        assert await service.is_holiday("NSE", date(2025, 1, 27)) is False

    async def test_next_trading_day(self, service: TradingCalendarService):
        await service.add_holiday("NSE", date(2025, 1, 27))
        next_day = await service.get_next_trading_day("NSE", date(2025, 1, 26))
        assert next_day == date(2025, 1, 28)

    async def test_bulk_add_holidays(self, service: TradingCalendarService):
        entries = await service.add_holidays_bulk([
            {"exchange": "NSE", "holiday_date": date(2025, 1, 26)},
            {"exchange": "NSE", "holiday_date": date(2025, 8, 15)},
        ])
        assert len(entries) == 2

    async def test_update_holiday(self, service: TradingCalendarService):
        h = await service.add_holiday("NSE", date(2025, 1, 26))
        updated = await service.update_holiday(h.id, description="Updated")
        assert updated is not None
        assert updated.description == "Updated"

    async def test_update_holiday_not_found(self, service: TradingCalendarService):
        assert await service.update_holiday(999, description="X") is None

    async def test_delete_holiday(self, service: TradingCalendarService):
        h = await service.add_holiday("NSE", date(2025, 1, 26))
        assert await service.delete_holiday(h.id) is True
        assert await service.get_holiday(h.id) is None

    async def test_delete_holiday_not_found(self, service: TradingCalendarService):
        assert await service.delete_holiday(999) is False


class TestSpecialSessions:
    async def test_add_special_session(self, service: TradingCalendarService):
        s = await service.add_special_session(
            "NSE", date(2025, 12, 31), "half_day",
            start_time=time(9, 0), end_time=time(12, 0),
            description="Early close",
        )
        assert s.exchange == "NSE"
        assert s.session_type == "half_day"
        assert s.start_time == time(9, 0)

    async def test_add_special_session_duplicate(self, service: TradingCalendarService):
        s1 = await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        s2 = await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        assert s2.id == s1.id

    async def test_get_special_session(self, service: TradingCalendarService):
        s = await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        found = await service.get_special_session(s.id)
        assert found is not None

    async def test_list_special_sessions(self, service: TradingCalendarService):
        await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        await service.add_special_session("NSE", date(2025, 12, 24), "early_close")
        lst = await service.list_special_sessions(exchange="NSE")
        assert len(lst) == 2

    async def test_list_special_sessions_date_range(self, service: TradingCalendarService):
        await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        await service.add_special_session("NSE", date(2025, 11, 24), "early_close")
        lst = await service.list_special_sessions(from_date=date(2025, 12, 1))
        assert len(lst) == 1

    async def test_update_special_session(self, service: TradingCalendarService):
        s = await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        updated = await service.update_special_session(s.id, description="Changed")
        assert updated is not None
        assert updated.description == "Changed"

    async def test_delete_special_session(self, service: TradingCalendarService):
        s = await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        assert await service.delete_special_session(s.id) is True


class TestExpiryCalendar:
    async def test_add_expiry(self, service: TradingCalendarService):
        e = await service.add_expiry(
            "NSE", "index_futures", "NIFTY", date(2025, 3, 27),
            contract_month="MAR25", contract_code="NIFTY25MARFUT",
        )
        assert e.exchange == "NSE"
        assert e.underlying == "NIFTY"
        assert e.expiry_date == date(2025, 3, 27)

    async def test_add_expiry_with_strike(self, service: TradingCalendarService):
        e = await service.add_expiry(
            "NSE", "index_options", "NIFTY", date(2025, 4, 3),
            strike_price=18000.0, option_type="CE",
        )
        assert e.strike_price == 18000.0
        assert e.option_type == "CE"

    async def test_add_expiry_duplicate(self, service: TradingCalendarService):
        e1 = await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        e2 = await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        assert e2.id == e1.id

    async def test_get_expiry(self, service: TradingCalendarService):
        e = await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        found = await service.get_expiry(e.id)
        assert found is not None

    async def test_list_expiries(self, service: TradingCalendarService):
        await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        await service.add_expiry("NSE", "index_futures", "BANKNIFTY", date(2025, 3, 26))
        lst = await service.list_expiries(exchange="NSE", instrument_type="index_futures")
        assert len(lst) == 2

    async def test_list_expiries_by_underlying(self, service: TradingCalendarService):
        await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        await service.add_expiry("NSE", "index_futures", "BANKNIFTY", date(2025, 3, 26))
        lst = await service.list_expiries(underlying="NIFTY")
        assert len(lst) == 1

    async def test_nearest_expiry(self, service: TradingCalendarService):
        from datetime import timedelta
        today = date.today()
        await service.add_expiry("NSE", "index_futures", "NIFTY", today + timedelta(days=30))
        await service.add_expiry("NSE", "index_futures", "NIFTY", today + timedelta(days=60))
        nearest = await service.get_nearest_expiry("NSE", "NIFTY")
        assert nearest is not None
        assert nearest.expiry_date == today + timedelta(days=30)

    async def test_nearest_expiry_no_upcoming(self, service: TradingCalendarService):
        await service.add_expiry("NSE", "index_futures", "NIFTY", date(2020, 3, 27))
        nearest = await service.get_nearest_expiry("NSE", "NIFTY")
        assert nearest is None

    async def test_bulk_add_expiries(self, service: TradingCalendarService):
        entries = await service.add_expiries_bulk([
            {"exchange": "NSE", "instrument_type": "index_futures",
             "underlying": "NIFTY", "expiry_date": date(2025, 3, 27)},
            {"exchange": "NSE", "instrument_type": "index_futures",
             "underlying": "BANKNIFTY", "expiry_date": date(2025, 3, 26)},
        ])
        assert len(entries) == 2

    async def test_update_expiry(self, service: TradingCalendarService):
        e = await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        updated = await service.update_expiry(e.id, strike_price=18500.0)
        assert updated is not None
        assert updated.strike_price == 18500.0

    async def test_delete_expiry(self, service: TradingCalendarService):
        e = await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        assert await service.delete_expiry(e.id) is True


class TestSettlementCalendar:
    async def test_add_settlement(self, service: TradingCalendarService):
        s = await service.add_settlement(
            "NSE", date(2025, 3, 27), date(2025, 3, 28),
            "T+1", segment="EQ",
        )
        assert s.exchange == "NSE"
        assert s.settlement_type == "T+1"
        assert s.trade_date == date(2025, 3, 27)
        assert s.settlement_date == date(2025, 3, 28)

    async def test_add_settlement_duplicate(self, service: TradingCalendarService):
        s1 = await service.add_settlement("NSE", date(2025, 3, 27), date(2025, 3, 28), "T+1")
        s2 = await service.add_settlement("NSE", date(2025, 3, 27), date(2025, 3, 28), "T+1")
        assert s2.id == s1.id

    async def test_get_settlement(self, service: TradingCalendarService):
        s = await service.add_settlement("NSE", date(2025, 3, 27), date(2025, 3, 28), "T+1")
        found = await service.get_settlement(s.id)
        assert found is not None

    async def test_list_settlements(self, service: TradingCalendarService):
        await service.add_settlement("NSE", date(2025, 3, 27), date(2025, 3, 28), "T+1")
        await service.add_settlement("NSE", date(2025, 3, 28), date(2025, 3, 31), "T+1")
        lst = await service.list_settlements(exchange="NSE")
        assert len(lst) == 2

    async def test_update_settlement(self, service: TradingCalendarService):
        s = await service.add_settlement("NSE", date(2025, 3, 27), date(2025, 3, 28), "T+1")
        updated = await service.update_settlement(s.id, description="Updated")
        assert updated is not None
        assert updated.description == "Updated"

    async def test_delete_settlement(self, service: TradingCalendarService):
        s = await service.add_settlement("NSE", date(2025, 3, 27), date(2025, 3, 28), "T+1")
        assert await service.delete_settlement(s.id) is True

    async def test_bulk_add_settlements(self, service: TradingCalendarService):
        entries = await service.add_settlements_bulk([
            {"exchange": "NSE", "trade_date": date(2025, 3, 27),
             "settlement_date": date(2025, 3, 28), "settlement_type": "T+1"},
            {"exchange": "NSE", "trade_date": date(2025, 3, 28),
             "settlement_date": date(2025, 3, 31), "settlement_type": "T+1"},
        ])
        assert len(entries) == 2


class TestCorporateCalendar:
    async def test_add_corporate_event(self, service: TradingCalendarService):
        e = await service.add_corporate_event(
            "RELIANCE", "dividend",
            announcement_date=date(2025, 3, 1),
            ex_date=date(2025, 3, 15),
            payment_date=date(2025, 4, 1),
            is_confirmed=True,
        )
        assert e.symbol == "RELIANCE"
        assert e.event_type == "dividend"
        assert e.ex_date == date(2025, 3, 15)

    async def test_get_corporate_event(self, service: TradingCalendarService):
        e = await service.add_corporate_event("TCS", "buyback")
        found = await service.get_corporate_event(e.id)
        assert found is not None

    async def test_list_corporate_events(self, service: TradingCalendarService):
        await service.add_corporate_event("RELIANCE", "dividend", ex_date=date(2025, 3, 15))
        await service.add_corporate_event("TCS", "dividend", ex_date=date(2025, 4, 1))
        await service.add_corporate_event("INFY", "buyback", ex_date=date(2025, 5, 1))
        lst = await service.list_corporate_events()
        assert len(lst) == 3

    async def test_list_corporate_events_by_symbol(self, service: TradingCalendarService):
        await service.add_corporate_event("RELIANCE", "dividend")
        await service.add_corporate_event("TCS", "dividend")
        lst = await service.list_corporate_events(symbol="RELIANCE")
        assert len(lst) == 1

    async def test_list_corporate_events_by_type(self, service: TradingCalendarService):
        await service.add_corporate_event("RELIANCE", "dividend")
        await service.add_corporate_event("TCS", "buyback")
        lst = await service.list_corporate_events(event_type="dividend")
        assert len(lst) == 1

    async def test_list_corporate_events_confirmed_only(self, service: TradingCalendarService):
        await service.add_corporate_event("RELIANCE", "dividend", is_confirmed=True)
        await service.add_corporate_event("TCS", "dividend", is_confirmed=False)
        lst = await service.list_corporate_events(confirmed_only=True)
        assert len(lst) == 1

    async def test_upcoming_events(self, service: TradingCalendarService):
        from datetime import timedelta
        today = date.today()
        await service.add_corporate_event("RELIANCE", "dividend", ex_date=today + timedelta(days=5))
        await service.add_corporate_event("TCS", "dividend", ex_date=today + timedelta(days=60))
        upcoming = await service.get_upcoming_events(days_ahead=30)
        assert len(upcoming) == 1

    async def test_bulk_add_corporate_events(self, service: TradingCalendarService):
        entries = await service.add_corporate_events_bulk([
            {"symbol": "RELIANCE", "event_type": "dividend"},
            {"symbol": "TCS", "event_type": "buyback"},
        ])
        assert len(entries) == 2

    async def test_update_corporate_event(self, service: TradingCalendarService):
        e = await service.add_corporate_event("RELIANCE", "dividend")
        updated = await service.update_corporate_event(e.id, is_confirmed=True)
        assert updated is not None
        assert updated.is_confirmed is True

    async def test_delete_corporate_event(self, service: TradingCalendarService):
        e = await service.add_corporate_event("RELIANCE", "dividend")
        assert await service.delete_corporate_event(e.id) is True


class TestUnifiedCalendar:
    async def test_daily_calendar(self, service: TradingCalendarService):
        await service.add_holiday("NSE", date(2025, 1, 26))
        cal = await service.get_daily_calendar("NSE", date(2025, 1, 26))
        assert cal["is_holiday"] is True
        assert cal["date"] == "2025-01-26"

    async def test_daily_calendar_with_special(self, service: TradingCalendarService):
        await service.add_special_session("NSE", date(2025, 12, 31), "half_day")
        cal = await service.get_daily_calendar("NSE", date(2025, 12, 31))
        assert cal["is_holiday"] is False
        assert len(cal["special_sessions"]) == 1

    async def test_daily_calendar_with_expiries(self, service: TradingCalendarService):
        await service.add_expiry("NSE", "index_futures", "NIFTY", date(2025, 3, 27))
        cal = await service.get_daily_calendar("NSE", date(2025, 3, 27))
        assert len(cal["expiries"]) == 1

    async def test_monthly_calendar(self, service: TradingCalendarService):
        await service.add_holiday("NSE", date(2025, 1, 26))
        cal = await service.get_month_calendar("NSE", 2025, 1)
        jan26 = [d for d in cal if d["date"] == "2025-01-26"]
        assert len(jan26) == 1
        assert jan26[0]["is_holiday"] is True
        assert len(cal) == 31
