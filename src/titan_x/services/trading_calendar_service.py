"""Trading Calendar service.

Manages trading holidays, special sessions, expiry calendars,
settlement calendars, and corporate calendars.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.trading_calendar import (
    CorporateCalendar,
    ExpiryCalendar,
    SettlementCalendar,
    SpecialSession,
    TradingHoliday,
)


# ── Service ──────────────────────────────────────────────────────────────────


class TradingCalendarService:
    """Service for all trading calendar operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ═════════════════════════════════════════════════════════════════════
    # Trading Holidays
    # ═════════════════════════════════════════════════════════════════════

    async def add_holiday(
        self, exchange: str, holiday_date: date,
        description: str | None = None,
        segment: str | None = None,
        is_recurring: bool = False,
    ) -> TradingHoliday:
        existing = await self._find_holiday(exchange, holiday_date)
        if existing:
            return existing
        entry = TradingHoliday(
            exchange=exchange.upper(),
            holiday_date=holiday_date,
            description=description,
            segment=segment,
            year=holiday_date.year,
            is_recurring=is_recurring,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def add_holidays_bulk(
        self, holidays: list[dict[str, Any]],
    ) -> list[TradingHoliday]:
        results: list[TradingHoliday] = []
        for h in holidays:
            entry = await self.add_holiday(
                exchange=h["exchange"],
                holiday_date=h["holiday_date"],
                description=h.get("description"),
                segment=h.get("segment"),
                is_recurring=h.get("is_recurring", False),
            )
            results.append(entry)
        return results

    async def get_holiday(self, holiday_id: int) -> TradingHoliday | None:
        result = await self.session.execute(
            select(TradingHoliday).where(TradingHoliday.id == holiday_id)
        )
        return result.scalar_one_or_none()

    async def list_holidays(
        self, exchange: str | None = None,
        year: int | None = None,
        active_only: bool = True,
    ) -> list[TradingHoliday]:
        stmt = select(TradingHoliday).order_by(TradingHoliday.holiday_date)
        if exchange:
            stmt = stmt.where(TradingHoliday.exchange == exchange.upper())
        if year:
            stmt = stmt.where(TradingHoliday.year == year)
        if active_only:
            stmt = stmt.where(TradingHoliday.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def is_holiday(self, exchange: str, check_date: date) -> bool:
        result = await self.session.execute(
            select(TradingHoliday).where(
                TradingHoliday.exchange == exchange.upper(),
                TradingHoliday.holiday_date == check_date,
                TradingHoliday.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none() is not None

    async def update_holiday(
        self, holiday_id: int, **kwargs: Any,
    ) -> TradingHoliday | None:
        entry = await self.get_holiday(holiday_id)
        if not entry:
            return None
        for k, v in kwargs.items():
            if hasattr(entry, k) and v is not None:
                setattr(entry, k, v)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_holiday(self, holiday_id: int) -> bool:
        entry = await self.get_holiday(holiday_id)
        if not entry:
            return False
        await self.session.delete(entry)
        await self.session.commit()
        return True

    async def get_next_trading_day(
        self, exchange: str, from_date: date,
    ) -> date | None:
        cur = from_date
        max_lookahead = 30
        for _ in range(max_lookahead):
            cur = cur.__add__(__import__("datetime").timedelta(days=1))
            if not await self.is_holiday(exchange, cur):
                return cur
        return None

    # ═════════════════════════════════════════════════════════════════════
    # Special Sessions
    # ═════════════════════════════════════════════════════════════════════

    async def add_special_session(
        self, exchange: str, session_date: date,
        session_type: str,
        start_time: time | None = None,
        end_time: time | None = None,
        description: str | None = None,
        segment: str | None = None,
    ) -> SpecialSession:
        existing = await self._find_special_session(
            exchange, session_date, session_type,
        )
        if existing:
            return existing
        entry = SpecialSession(
            exchange=exchange.upper(),
            session_date=session_date,
            session_type=session_type,
            start_time=start_time,
            end_time=end_time,
            description=description,
            segment=segment,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def get_special_session(self, session_id: int) -> SpecialSession | None:
        result = await self.session.execute(
            select(SpecialSession).where(SpecialSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_special_sessions(
        self, exchange: str | None = None,
        session_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        active_only: bool = True,
    ) -> list[SpecialSession]:
        stmt = select(SpecialSession).order_by(
            SpecialSession.session_date, SpecialSession.session_type,
        )
        if exchange:
            stmt = stmt.where(SpecialSession.exchange == exchange.upper())
        if session_type:
            stmt = stmt.where(SpecialSession.session_type == session_type)
        if from_date:
            stmt = stmt.where(SpecialSession.session_date >= from_date)
        if to_date:
            stmt = stmt.where(SpecialSession.session_date <= to_date)
        if active_only:
            stmt = stmt.where(SpecialSession.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_special_session(
        self, session_id: int, **kwargs: Any,
    ) -> SpecialSession | None:
        entry = await self.get_special_session(session_id)
        if not entry:
            return None
        for k, v in kwargs.items():
            if hasattr(entry, k) and v is not None:
                setattr(entry, k, v)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_special_session(self, session_id: int) -> bool:
        entry = await self.get_special_session(session_id)
        if not entry:
            return False
        await self.session.delete(entry)
        await self.session.commit()
        return True

    # ═════════════════════════════════════════════════════════════════════
    # Expiry Calendar
    # ═════════════════════════════════════════════════════════════════════

    async def add_expiry(
        self, exchange: str, instrument_type: str,
        underlying: str, expiry_date: date,
        contract_month: str | None = None,
        contract_code: str | None = None,
        strike_price: float | None = None,
        option_type: str | None = None,
    ) -> ExpiryCalendar:
        existing = await self._find_expiry(
            exchange, instrument_type, underlying, expiry_date,
        )
        if existing:
            return existing
        entry = ExpiryCalendar(
            exchange=exchange.upper(),
            instrument_type=instrument_type,
            underlying=underlying,
            contract_month=contract_month,
            expiry_date=expiry_date,
            contract_code=contract_code,
            strike_price=strike_price,
            option_type=option_type,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def add_expiries_bulk(
        self, expiries: list[dict[str, Any]],
    ) -> list[ExpiryCalendar]:
        results: list[ExpiryCalendar] = []
        for e in expiries:
            entry = await self.add_expiry(
                exchange=e["exchange"],
                instrument_type=e["instrument_type"],
                underlying=e["underlying"],
                expiry_date=e["expiry_date"],
                contract_month=e.get("contract_month"),
                contract_code=e.get("contract_code"),
                strike_price=e.get("strike_price"),
                option_type=e.get("option_type"),
            )
            results.append(entry)
        return results

    async def get_expiry(self, expiry_id: int) -> ExpiryCalendar | None:
        result = await self.session.execute(
            select(ExpiryCalendar).where(ExpiryCalendar.id == expiry_id)
        )
        return result.scalar_one_or_none()

    async def list_expiries(
        self, exchange: str | None = None,
        instrument_type: str | None = None,
        underlying: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        active_only: bool = True,
    ) -> list[ExpiryCalendar]:
        stmt = select(ExpiryCalendar).order_by(
            ExpiryCalendar.expiry_date, ExpiryCalendar.underlying,
        )
        if exchange:
            stmt = stmt.where(ExpiryCalendar.exchange == exchange.upper())
        if instrument_type:
            stmt = stmt.where(ExpiryCalendar.instrument_type == instrument_type)
        if underlying:
            stmt = stmt.where(ExpiryCalendar.underlying == underlying)
        if from_date:
            stmt = stmt.where(ExpiryCalendar.expiry_date >= from_date)
        if to_date:
            stmt = stmt.where(ExpiryCalendar.expiry_date <= to_date)
        if active_only:
            stmt = stmt.where(ExpiryCalendar.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_nearest_expiry(
        self, exchange: str, underlying: str,
        instrument_type: str = "index_futures",
    ) -> ExpiryCalendar | None:
        today = date.today()
        result = await self.session.execute(
            select(ExpiryCalendar)
            .where(
                ExpiryCalendar.exchange == exchange.upper(),
                ExpiryCalendar.underlying == underlying,
                ExpiryCalendar.instrument_type == instrument_type,
                ExpiryCalendar.expiry_date >= today,
                ExpiryCalendar.is_active.is_(True),
            )
            .order_by(ExpiryCalendar.expiry_date)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_expiry(
        self, expiry_id: int, **kwargs: Any,
    ) -> ExpiryCalendar | None:
        entry = await self.get_expiry(expiry_id)
        if not entry:
            return None
        for k, v in kwargs.items():
            if hasattr(entry, k) and v is not None:
                setattr(entry, k, v)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_expiry(self, expiry_id: int) -> bool:
        entry = await self.get_expiry(expiry_id)
        if not entry:
            return False
        await self.session.delete(entry)
        await self.session.commit()
        return True

    # ═════════════════════════════════════════════════════════════════════
    # Settlement Calendar
    # ═════════════════════════════════════════════════════════════════════

    async def add_settlement(
        self, exchange: str, trade_date: date,
        settlement_date: date, settlement_type: str,
        segment: str | None = None,
        description: str | None = None,
    ) -> SettlementCalendar:
        existing = await self._find_settlement(
            exchange, trade_date, settlement_type,
        )
        if existing:
            return existing
        entry = SettlementCalendar(
            exchange=exchange.upper(),
            trade_date=trade_date,
            settlement_date=settlement_date,
            settlement_type=settlement_type,
            segment=segment,
            description=description,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def add_settlements_bulk(
        self, settlements: list[dict[str, Any]],
    ) -> list[SettlementCalendar]:
        results: list[SettlementCalendar] = []
        for s in settlements:
            entry = await self.add_settlement(
                exchange=s["exchange"],
                trade_date=s["trade_date"],
                settlement_date=s["settlement_date"],
                settlement_type=s["settlement_type"],
                segment=s.get("segment"),
                description=s.get("description"),
            )
            results.append(entry)
        return results

    async def get_settlement(self, settlement_id: int) -> SettlementCalendar | None:
        result = await self.session.execute(
            select(SettlementCalendar).where(SettlementCalendar.id == settlement_id)
        )
        return result.scalar_one_or_none()

    async def list_settlements(
        self, exchange: str | None = None,
        settlement_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SettlementCalendar]:
        stmt = select(SettlementCalendar).order_by(
            SettlementCalendar.trade_date, SettlementCalendar.settlement_type,
        )
        if exchange:
            stmt = stmt.where(SettlementCalendar.exchange == exchange.upper())
        if settlement_type:
            stmt = stmt.where(
                SettlementCalendar.settlement_type == settlement_type,
            )
        if from_date:
            stmt = stmt.where(SettlementCalendar.trade_date >= from_date)
        if to_date:
            stmt = stmt.where(SettlementCalendar.trade_date <= to_date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_settlement(
        self, settlement_id: int, **kwargs: Any,
    ) -> SettlementCalendar | None:
        entry = await self.get_settlement(settlement_id)
        if not entry:
            return None
        for k, v in kwargs.items():
            if hasattr(entry, k) and v is not None:
                setattr(entry, k, v)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_settlement(self, settlement_id: int) -> bool:
        entry = await self.get_settlement(settlement_id)
        if not entry:
            return False
        await self.session.delete(entry)
        await self.session.commit()
        return True

    # ═════════════════════════════════════════════════════════════════════
    # Corporate Calendar
    # ═════════════════════════════════════════════════════════════════════

    async def add_corporate_event(
        self, symbol: str, event_type: str,
        announcement_date: date | None = None,
        record_date: date | None = None,
        ex_date: date | None = None,
        payment_date: date | None = None,
        description: str | None = None,
        details_json: str | None = None,
        source: str | None = None,
        is_confirmed: bool = False,
    ) -> CorporateCalendar:
        entry = CorporateCalendar(
            symbol=symbol.upper(),
            event_type=event_type,
            announcement_date=announcement_date,
            record_date=record_date,
            ex_date=ex_date,
            payment_date=payment_date,
            description=description,
            details_json=details_json,
            source=source,
            is_confirmed=is_confirmed,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def add_corporate_events_bulk(
        self, events: list[dict[str, Any]],
    ) -> list[CorporateCalendar]:
        results: list[CorporateCalendar] = []
        for ev in events:
            entry = await self.add_corporate_event(
                symbol=ev["symbol"],
                event_type=ev["event_type"],
                announcement_date=ev.get("announcement_date"),
                record_date=ev.get("record_date"),
                ex_date=ev.get("ex_date"),
                payment_date=ev.get("payment_date"),
                description=ev.get("description"),
                details_json=ev.get("details_json"),
                source=ev.get("source"),
                is_confirmed=ev.get("is_confirmed", False),
            )
            results.append(entry)
        return results

    async def get_corporate_event(self, event_id: int) -> CorporateCalendar | None:
        result = await self.session.execute(
            select(CorporateCalendar).where(CorporateCalendar.id == event_id)
        )
        return result.scalar_one_or_none()

    async def list_corporate_events(
        self, symbol: str | None = None,
        event_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        confirmed_only: bool = False,
    ) -> list[CorporateCalendar]:
        stmt = select(CorporateCalendar).order_by(
            CorporateCalendar.ex_date.desc().nullslast(),
            CorporateCalendar.announcement_date.desc().nullslast(),
        )
        if symbol:
            stmt = stmt.where(CorporateCalendar.symbol == symbol.upper())
        if event_type:
            stmt = stmt.where(CorporateCalendar.event_type == event_type)
        if from_date:
            stmt = stmt.where(
                CorporateCalendar.ex_date >= from_date,
            )
        if to_date:
            stmt = stmt.where(
                CorporateCalendar.ex_date <= to_date,
            )
        if confirmed_only:
            stmt = stmt.where(CorporateCalendar.is_confirmed.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_corporate_event(
        self, event_id: int, **kwargs: Any,
    ) -> CorporateCalendar | None:
        entry = await self.get_corporate_event(event_id)
        if not entry:
            return None
        for k, v in kwargs.items():
            if hasattr(entry, k) and v is not None:
                setattr(entry, k, v)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_corporate_event(self, event_id: int) -> bool:
        entry = await self.get_corporate_event(event_id)
        if not entry:
            return False
        await self.session.delete(entry)
        await self.session.commit()
        return True

    async def get_upcoming_events(
        self, days_ahead: int = 30,
    ) -> list[CorporateCalendar]:
        today = date.today()
        from datetime import timedelta
        limit = today + timedelta(days=days_ahead)
        result = await self.session.execute(
            select(CorporateCalendar)
            .where(
                CorporateCalendar.ex_date >= today,
                CorporateCalendar.ex_date <= limit,
            )
            .order_by(CorporateCalendar.ex_date)
        )
        return list(result.scalars().all())

    # ═════════════════════════════════════════════════════════════════════
    # Helpers — unified calendar
    # ═════════════════════════════════════════════════════════════════════

    async def get_daily_calendar(
        self, exchange: str, calendar_date: date,
    ) -> dict[str, Any]:
        is_holiday = await self.is_holiday(exchange, calendar_date)
        special = await self.list_special_sessions(
            exchange=exchange, from_date=calendar_date, to_date=calendar_date,
        )
        expiries = await self.list_expiries(
            exchange=exchange, from_date=calendar_date, to_date=calendar_date,
        )
        settlements = await self.list_settlements(
            exchange=exchange, from_date=calendar_date, to_date=calendar_date,
        )
        return {
            "date": calendar_date.isoformat(),
            "is_holiday": is_holiday,
            "special_sessions": [_ss_dict(s) for s in special],
            "expiries": [_exp_dict(e) for e in expiries],
            "settlements": [_set_dict(s) for s in settlements],
        }

    async def get_month_calendar(
        self, exchange: str, year: int, month: int,
    ) -> list[dict[str, Any]]:
        import calendar
        month_range = calendar.monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, month_range[1])
        results: list[dict[str, Any]] = []
        cur = start
        while cur <= end:
            results.append(await self.get_daily_calendar(exchange, cur))
            from datetime import timedelta
            cur += timedelta(days=1)
        return results

    # ═════════════════════════════════════════════════════════════════════
    # Internals
    # ═════════════════════════════════════════════════════════════════════

    async def _find_holiday(
        self, exchange: str, holiday_date: date,
    ) -> TradingHoliday | None:
        result = await self.session.execute(
            select(TradingHoliday).where(
                TradingHoliday.exchange == exchange.upper(),
                TradingHoliday.holiday_date == holiday_date,
            )
        )
        return result.scalar_one_or_none()

    async def _find_special_session(
        self, exchange: str, session_date: date, session_type: str,
    ) -> SpecialSession | None:
        result = await self.session.execute(
            select(SpecialSession).where(
                SpecialSession.exchange == exchange.upper(),
                SpecialSession.session_date == session_date,
                SpecialSession.session_type == session_type,
            )
        )
        return result.scalar_one_or_none()

    async def _find_expiry(
        self, exchange: str, instrument_type: str,
        underlying: str, expiry_date: date,
    ) -> ExpiryCalendar | None:
        result = await self.session.execute(
            select(ExpiryCalendar).where(
                ExpiryCalendar.exchange == exchange.upper(),
                ExpiryCalendar.instrument_type == instrument_type,
                ExpiryCalendar.underlying == underlying,
                ExpiryCalendar.expiry_date == expiry_date,
            )
        )
        return result.scalar_one_or_none()

    async def _find_settlement(
        self, exchange: str, trade_date: date, settlement_type: str,
    ) -> SettlementCalendar | None:
        result = await self.session.execute(
            select(SettlementCalendar).where(
                SettlementCalendar.exchange == exchange.upper(),
                SettlementCalendar.trade_date == trade_date,
                SettlementCalendar.settlement_type == settlement_type,
            )
        )
        return result.scalar_one_or_none()


# ── Serializer helpers ───────────────────────────────────────────────────────


def _ss_dict(s: SpecialSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "exchange": s.exchange,
        "session_date": s.session_date.isoformat(),
        "session_type": s.session_type,
        "start_time": s.start_time.isoformat() if s.start_time else None,
        "end_time": s.end_time.isoformat() if s.end_time else None,
        "description": s.description,
        "segment": s.segment,
    }


def _exp_dict(e: ExpiryCalendar) -> dict[str, Any]:
    return {
        "id": e.id,
        "exchange": e.exchange,
        "instrument_type": e.instrument_type,
        "underlying": e.underlying,
        "contract_month": e.contract_month,
        "expiry_date": e.expiry_date.isoformat(),
        "contract_code": e.contract_code,
        "strike_price": e.strike_price,
        "option_type": e.option_type,
    }


def _set_dict(s: SettlementCalendar) -> dict[str, Any]:
    return {
        "id": s.id,
        "exchange": s.exchange,
        "trade_date": s.trade_date.isoformat(),
        "settlement_date": s.settlement_date.isoformat(),
        "settlement_type": s.settlement_type,
        "segment": s.segment,
        "description": s.description,
    }
