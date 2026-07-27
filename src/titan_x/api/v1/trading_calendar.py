"""Trading Calendar API."""
from datetime import date, time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.trading_calendar_service import TradingCalendarService

router = APIRouter(prefix="/trading-calendar", tags=["trading_calendar"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> TradingCalendarService:
    return TradingCalendarService(session)


# ── Holidays ─────────────────────────────────────────────────────────────────


@router.get("/holidays")
async def list_holidays(
    exchange: str | None = None,
    year: int | None = None,
    active_only: bool = True,
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.list_holidays(exchange, year, active_only)
    return [_h_dict(h) for h in entries]


@router.get("/holidays/check")
async def check_holiday(
    exchange: str = Query(..., description="Exchange code"),
    check_date: date = Query(..., description="Date to check"),
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    is_holiday = await service.is_holiday(exchange, check_date)
    return {"exchange": exchange.upper(), "date": check_date.isoformat(), "is_holiday": is_holiday}


@router.get("/holidays/next-trading-day")
async def next_trading_day(
    exchange: str = Query(..., description="Exchange code"),
    from_date: date = Query(..., description="Starting date"),
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    result = await service.get_next_trading_day(exchange, from_date)
    if result is None:
        raise HTTPException(status_code=404, detail="No trading day found within lookahead window")
    return {"exchange": exchange.upper(), "from_date": from_date.isoformat(), "next_trading_day": result.isoformat()}


@router.get("/holidays/{holiday_id}")
async def get_holiday(
    holiday_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.get_holiday(holiday_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return _h_dict(entry)


@router.post("/holidays")
async def create_holiday(
    exchange: str,
    holiday_date: date,
    description: str | None = None,
    segment: str | None = None,
    is_recurring: bool = False,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.add_holiday(exchange, holiday_date, description, segment, is_recurring)
    return _h_dict(entry)


@router.post("/holidays/bulk")
async def create_holidays_bulk(
    holidays: list[dict[str, Any]],
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.add_holidays_bulk(holidays)
    return [_h_dict(e) for e in entries]


@router.put("/holidays/{holiday_id}")
async def update_holiday(
    holiday_id: int,
    updates: dict[str, Any],
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.update_holiday(holiday_id, **updates)
    if not entry:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return _h_dict(entry)


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    deleted = await service.delete_holiday(holiday_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"deleted": True}


# ── Special Sessions ─────────────────────────────────────────────────────────


@router.get("/special-sessions")
async def list_special_sessions(
    exchange: str | None = None,
    session_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    active_only: bool = True,
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.list_special_sessions(exchange, session_type, from_date, to_date, active_only)
    return [_ss_dict(e) for e in entries]


@router.get("/special-sessions/{session_id}")
async def get_special_session(
    session_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.get_special_session(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Special session not found")
    return _ss_dict(entry)


@router.post("/special-sessions")
async def create_special_session(
    exchange: str,
    session_date: date,
    session_type: str,
    start_time: time | None = None,
    end_time: time | None = None,
    description: str | None = None,
    segment: str | None = None,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.add_special_session(exchange, session_date, session_type, start_time, end_time, description, segment)
    return _ss_dict(entry)


@router.put("/special-sessions/{session_id}")
async def update_special_session(
    session_id: int,
    updates: dict[str, Any],
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.update_special_session(session_id, **updates)
    if not entry:
        raise HTTPException(status_code=404, detail="Special session not found")
    return _ss_dict(entry)


@router.delete("/special-sessions/{session_id}")
async def delete_special_session(
    session_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    deleted = await service.delete_special_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Special session not found")
    return {"deleted": True}


# ── Expiry Calendar ──────────────────────────────────────────────────────────


@router.get("/expiries")
async def list_expiries(
    exchange: str | None = None,
    instrument_type: str | None = None,
    underlying: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    active_only: bool = True,
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.list_expiries(exchange, instrument_type, underlying, from_date, to_date, active_only)
    return [_exp_dict(e) for e in entries]


@router.get("/expiries/nearest")
async def nearest_expiry(
    exchange: str = Query(...),
    underlying: str = Query(...),
    instrument_type: str = "index_futures",
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.get_nearest_expiry(exchange, underlying, instrument_type)
    if not entry:
        raise HTTPException(status_code=404, detail="No upcoming expiry found")
    return _exp_dict(entry)


@router.get("/expiries/{expiry_id}")
async def get_expiry(
    expiry_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.get_expiry(expiry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Expiry not found")
    return _exp_dict(entry)


@router.post("/expiries")
async def create_expiry(
    exchange: str,
    instrument_type: str,
    underlying: str,
    expiry_date: date,
    contract_month: str | None = None,
    contract_code: str | None = None,
    strike_price: float | None = None,
    option_type: str | None = None,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.add_expiry(exchange, instrument_type, underlying, expiry_date, contract_month, contract_code, strike_price, option_type)
    return _exp_dict(entry)


@router.post("/expiries/bulk")
async def create_expiries_bulk(
    expiries: list[dict[str, Any]],
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.add_expiries_bulk(expiries)
    return [_exp_dict(e) for e in entries]


@router.put("/expiries/{expiry_id}")
async def update_expiry(
    expiry_id: int,
    updates: dict[str, Any],
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.update_expiry(expiry_id, **updates)
    if not entry:
        raise HTTPException(status_code=404, detail="Expiry not found")
    return _exp_dict(entry)


@router.delete("/expiries/{expiry_id}")
async def delete_expiry(
    expiry_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    deleted = await service.delete_expiry(expiry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Expiry not found")
    return {"deleted": True}


# ── Settlement Calendar ──────────────────────────────────────────────────────


@router.get("/settlements")
async def list_settlements(
    exchange: str | None = None,
    settlement_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.list_settlements(exchange, settlement_type, from_date, to_date)
    return [_set_dict(e) for e in entries]


@router.get("/settlements/{settlement_id}")
async def get_settlement(
    settlement_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.get_settlement(settlement_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Settlement not found")
    return _set_dict(entry)


@router.post("/settlements")
async def create_settlement(
    exchange: str,
    trade_date: date,
    settlement_date: date,
    settlement_type: str,
    segment: str | None = None,
    description: str | None = None,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.add_settlement(exchange, trade_date, settlement_date, settlement_type, segment, description)
    return _set_dict(entry)


@router.post("/settlements/bulk")
async def create_settlements_bulk(
    settlements: list[dict[str, Any]],
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.add_settlements_bulk(settlements)
    return [_set_dict(e) for e in entries]


@router.put("/settlements/{settlement_id}")
async def update_settlement(
    settlement_id: int,
    updates: dict[str, Any],
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.update_settlement(settlement_id, **updates)
    if not entry:
        raise HTTPException(status_code=404, detail="Settlement not found")
    return _set_dict(entry)


@router.delete("/settlements/{settlement_id}")
async def delete_settlement(
    settlement_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    deleted = await service.delete_settlement(settlement_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Settlement not found")
    return {"deleted": True}


# ── Corporate Calendar ───────────────────────────────────────────────────────


@router.get("/corporate-events")
async def list_corporate_events(
    symbol: str | None = None,
    event_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    confirmed_only: bool = False,
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.list_corporate_events(symbol, event_type, from_date, to_date, confirmed_only)
    return [_ce_dict(e) for e in entries]


@router.get("/corporate-events/upcoming")
async def upcoming_events(
    days_ahead: int = Query(30, description="Number of days ahead"),
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.get_upcoming_events(days_ahead)
    return [_ce_dict(e) for e in entries]


@router.get("/corporate-events/{event_id}")
async def get_corporate_event(
    event_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.get_corporate_event(event_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Corporate event not found")
    return _ce_dict(entry)


@router.post("/corporate-events")
async def create_corporate_event(
    symbol: str,
    event_type: str,
    announcement_date: date | None = None,
    record_date: date | None = None,
    ex_date: date | None = None,
    payment_date: date | None = None,
    description: str | None = None,
    details_json: str | None = None,
    source: str | None = None,
    is_confirmed: bool = False,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.add_corporate_event(symbol, event_type, announcement_date, record_date, ex_date, payment_date, description, details_json, source, is_confirmed)
    return _ce_dict(entry)


@router.post("/corporate-events/bulk")
async def create_corporate_events_bulk(
    events: list[dict[str, Any]],
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.add_corporate_events_bulk(events)
    return [_ce_dict(e) for e in entries]


@router.put("/corporate-events/{event_id}")
async def update_corporate_event(
    event_id: int,
    updates: dict[str, Any],
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.update_corporate_event(event_id, **updates)
    if not entry:
        raise HTTPException(status_code=404, detail="Corporate event not found")
    return _ce_dict(entry)


@router.delete("/corporate-events/{event_id}")
async def delete_corporate_event(
    event_id: int,
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    deleted = await service.delete_corporate_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Corporate event not found")
    return {"deleted": True}


# ── Unified Calendar ─────────────────────────────────────────────────────────


@router.get("/daily")
async def daily_calendar(
    exchange: str = Query(...),
    calendar_date: date = Query(...),
    service: TradingCalendarService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.get_daily_calendar(exchange, calendar_date)


@router.get("/monthly")
async def monthly_calendar(
    exchange: str = Query(...),
    year: int = Query(...),
    month: int = Query(...),
    service: TradingCalendarService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return await service.get_month_calendar(exchange, year, month)


# ── Serialisers ──────────────────────────────────────────────────────────────


def _h_dict(h: Any) -> dict[str, Any]:
    return {
        "id": h.id,
        "exchange": h.exchange,
        "holiday_date": h.holiday_date.isoformat(),
        "description": h.description,
        "segment": h.segment,
        "year": h.year,
        "is_recurring": h.is_recurring,
        "is_active": h.is_active,
    }


def _ss_dict(s: Any) -> dict[str, Any]:
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


def _exp_dict(e: Any) -> dict[str, Any]:
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


def _set_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "exchange": s.exchange,
        "trade_date": s.trade_date.isoformat(),
        "settlement_date": s.settlement_date.isoformat(),
        "settlement_type": s.settlement_type,
        "segment": s.segment,
        "description": s.description,
    }


def _ce_dict(c: Any) -> dict[str, Any]:
    return {
        "id": c.id,
        "symbol": c.symbol,
        "event_type": c.event_type,
        "announcement_date": c.announcement_date.isoformat() if c.announcement_date else None,
        "record_date": c.record_date.isoformat() if c.record_date else None,
        "ex_date": c.ex_date.isoformat() if c.ex_date else None,
        "payment_date": c.payment_date.isoformat() if c.payment_date else None,
        "description": c.description,
        "details_json": c.details_json,
        "source": c.source,
        "is_confirmed": c.is_confirmed,
    }
