"""Tests for Corporate Reminder service."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from titan_x.db.base import Base
from titan_x.models.trading_calendar import CorporateCalendar, CorporateReminder
from titan_x.models.user import User
from titan_x.services.corporate_reminder_service import CorporateReminderService

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
async def user(session):
    u = User(
        email="test@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


@pytest_asyncio.fixture
async def service(session):
    return CorporateReminderService(session)


class TestEventRegistration:
    async def test_register_event(self, service: CorporateReminderService):
        e = await service.register_event("RELIANCE", "dividend", ex_date=date(2025, 6, 15))
        assert e.symbol == "RELIANCE"
        assert e.event_type == "dividend"
        assert e.ex_date == date(2025, 6, 15)

    async def test_register_event_invalid_type(self, service: CorporateReminderService):
        with pytest.raises(ValueError, match="Invalid event type"):
            await service.register_event("RELIANCE", "invalid_type", ex_date=date(2025, 6, 15))

    async def test_register_quarterly(self, service: CorporateReminderService):
        e = await service.register_quarterly("TCS", date(2025, 4, 10), quarter=4, fiscal_year=2025)
        assert e.event_type == "quarterly"
        assert e.ex_date == date(2025, 4, 10)
        assert 'quarter' in (e.details_json or "")

    async def test_register_agm(self, service: CorporateReminderService):
        e = await service.register_agm(
            "RELIANCE", date(2025, 8, 1),
            venue="Mumbai", chairman="Mukesh Ambani",
        )
        assert e.event_type == "agm"
        assert "Mumbai" in (e.details_json or "")

    async def test_register_agm_with_book_closure(self, service: CorporateReminderService):
        e = await service.register_agm(
            "RELIANCE", date(2025, 8, 1),
            book_closure_start=date(2025, 7, 25),
            book_closure_end=date(2025, 8, 1),
        )
        assert e.event_type == "agm"
        assert "book_closure_start" in (e.details_json or "")

    async def test_register_egm(self, service: CorporateReminderService):
        e = await service.register_egm(
            "INFY", date(2025, 3, 15),
            purpose="Approve buyback",
        )
        assert e.event_type == "egm"
        assert "buyback" in (e.description or "")

    async def test_register_dividend(self, service: CorporateReminderService):
        e = await service.register_dividend(
            "HDFC", date(2025, 5, 10),
            record_date=date(2025, 5, 12),
            amount_per_share=19.50, dividend_type="final",
        )
        assert e.event_type == "dividend"
        assert e.ex_date == date(2025, 5, 10)
        assert e.record_date == date(2025, 5, 12)

    async def test_register_split(self, service: CorporateReminderService):
        e = await service.register_split(
            "ABC", date(2025, 6, 1),
            old_face_value=10.0, new_face_value=1.0,
            ratio_numerator=10, ratio_denominator=1,
        )
        assert e.event_type == "split"
        assert "10:1" in (e.description or "")

    async def test_register_bonus(self, service: CorporateReminderService):
        e = await service.register_bonus(
            "XYZ", date(2025, 7, 1),
            ratio_numerator=1, ratio_denominator=2,
        )
        assert e.event_type == "bonus"
        assert "1:2" in (e.description or "")

    async def test_register_rights(self, service: CorporateReminderService):
        e = await service.register_rights(
            "PQR", date(2025, 8, 1),
            entitlement_ratio_numerator=1, entitlement_ratio_denominator=4,
            issue_price=150.0,
        )
        assert e.event_type == "rights"
        assert "1:4" in (e.description or "")
        assert "150" in (e.description or "")

    async def test_get_event(self, service: CorporateReminderService):
        e = await service.register_event("RELIANCE", "dividend", ex_date=date(2025, 6, 15))
        found = await service.get_event(e.id)
        assert found is not None
        assert found.id == e.id

    async def test_get_event_not_found(self, service: CorporateReminderService):
        assert await service.get_event(999) is None

    async def test_list_events(self, service: CorporateReminderService):
        await service.register_dividend("RELIANCE", date(2025, 6, 15))
        await service.register_split("TCS", date(2025, 7, 1))
        await service.register_bonus("INFY", date(2025, 8, 1))
        lst = await service.list_events()
        assert len(lst) == 3

    async def test_list_events_filter_by_type(self, service: CorporateReminderService):
        await service.register_dividend("RELIANCE", date(2025, 6, 15))
        await service.register_split("TCS", date(2025, 7, 1))
        divs = await service.list_events(event_type="dividend")
        assert len(divs) == 1

    async def test_list_events_filter_by_symbol(self, service: CorporateReminderService):
        await service.register_dividend("RELIANCE", date(2025, 6, 15))
        await service.register_dividend("TCS", date(2025, 7, 1))
        rel = await service.list_events(symbol="RELIANCE")
        assert len(rel) == 1

    async def test_list_events_filter_by_date_range(self, service: CorporateReminderService):
        await service.register_dividend("RELIANCE", date(2025, 6, 15))
        await service.register_dividend("TCS", date(2025, 7, 1))
        june = await service.list_events(from_date=date(2025, 6, 1), to_date=date(2025, 6, 30))
        assert len(june) == 1

    async def test_list_events_confirmed_only(self, service: CorporateReminderService):
        await service.register_event("RELIANCE", "dividend", ex_date=date(2025, 6, 15), is_confirmed=True)
        await service.register_event("TCS", "dividend", ex_date=date(2025, 7, 1), is_confirmed=False)
        confirmed = await service.list_events(confirmed_only=True)
        assert len(confirmed) == 1


class TestReminderSubscriptions:
    async def test_subscribe(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        reminder = await service.subscribe(user_id=user.id, event_id=e.id, days_before=7)
        assert reminder.user_id == user.id
        assert reminder.event_id == e.id
        assert reminder.days_before == 7
        assert reminder.reminder_date == date(2025, 6, 8)
        assert reminder.status == "pending"

    async def test_subscribe_invalid_user_auto(self, service: CorporateReminderService, user: User):
        with pytest.raises(ValueError, match="not found"):
            await service.subscribe(user_id=user.id, event_id=999)

    async def test_subscribe_duplicate(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        r1 = await service.subscribe(user.id, e.id, 7)
        r2 = await service.subscribe(user.id, e.id, 7)
        assert r2.id == r1.id

    async def test_subscribe_multi(self, service: CorporateReminderService, user: User):
        e1 = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        e2 = await service.register_split("TCS", date(2025, 7, 1))
        reminders = await service.subscribe_multi(user.id, [e1.id, e2.id])
        assert len(reminders) == 2

    async def test_unsubscribe(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        r = await service.subscribe(user.id, e.id)
        assert await service.unsubscribe(r.id) is True
        assert await service.unsubscribe(r.id) is False

    async def test_get_user_reminders(self, service: CorporateReminderService, user: User):
        e1 = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        e2 = await service.register_split("TCS", date(2025, 7, 1))
        await service.subscribe(user.id, e1.id)
        await service.subscribe(user.id, e2.id)
        u1 = await service.get_user_reminders(user.id)
        assert len(u1) == 2

    async def test_get_user_reminders_filter_status(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        await service.subscribe(user.id, e.id)
        pending = await service.get_user_reminders(user.id, status="pending")
        assert len(pending) == 1
        sent = await service.get_user_reminders(user.id, status="sent")
        assert len(sent) == 0

    async def test_acknowledge(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        r = await service.subscribe(user.id, e.id)
        assert await service.acknowledge(r.id) is True
        reminders = await service.get_user_reminders(user.id, status="acknowledged")
        assert len(reminders) == 1

    async def test_acknowledge_not_found(self, service: CorporateReminderService):
        assert await service.acknowledge(999) is False


class TestReminderGeneration:
    async def test_generate_reminders_no_notify(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", ex_date=date.today() + timedelta(days=3))
        await service.subscribe(user.id, e.id, days_before=5)
        result = await service.generate_reminders()
        assert result["reminders_found"] == 1
        assert result["notifications_sent"] == 1

    async def test_generate_reminders_future_not_due(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", ex_date=date.today() + timedelta(days=30))
        await service.subscribe(user.id, e.id, days_before=7)
        result = await service.generate_reminders()
        assert result["reminders_found"] == 0

    async def test_generate_reminders_specific_date(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", ex_date=date(2025, 6, 15))
        await service.subscribe(user.id, e.id, days_before=7)
        result = await service.generate_reminders(target_date=date(2025, 6, 8))
        assert result["reminders_found"] == 1

    async def test_generate_reminders_sets_status(self, service: CorporateReminderService, user: User):
        e = await service.register_dividend("RELIANCE", ex_date=date.today() + timedelta(days=3))
        r = await service.subscribe(user.id, e.id, days_before=5)
        assert r.status == "pending"
        await service.generate_reminders()
        reminders = await service.get_user_reminders(user.id)
        assert reminders[0].status == "sent"
        assert reminders[0].sent_at is not None


class TestReminderStats:
    async def test_stats(self, service: CorporateReminderService, user: User):
        e1 = await service.register_dividend("RELIANCE", date(2025, 6, 15))
        e2 = await service.register_split("TCS", date(2025, 7, 1))
        e3 = await service.register_bonus("INFY", date(2025, 8, 1))
        await service.subscribe(user.id, e1.id)
        await service.subscribe(user.id, e2.id)
        await service.subscribe(user.id, e3.id)
        stats = await service.get_reminder_stats()
        assert stats["total"] == 3
        assert stats["pending"] == 3
        assert stats["sent"] == 0
        assert "dividend" in stats["by_event_type"]
        assert "split" in stats["by_event_type"]
        assert "bonus" in stats["by_event_type"]


class TestAllEventTypes:
    async def test_all_seven_types(self, service: CorporateReminderService):
        await service.register_quarterly("TCS", date(2025, 4, 10))
        await service.register_agm("RELIANCE", date(2025, 8, 1))
        await service.register_egm("INFY", date(2025, 3, 15))
        await service.register_dividend("HDFC", date(2025, 5, 10))
        await service.register_split("ABC", date(2025, 6, 1))
        await service.register_bonus("XYZ", date(2025, 7, 1))
        await service.register_rights("PQR", date(2025, 8, 1))
        all_events = await service.list_events()
        assert len(all_events) == 7
        types = {e.event_type for e in all_events}
        assert types == {"quarterly", "agm", "egm", "dividend", "split", "bonus", "rights"}
