"""Corporate Event Reminders API.

Endpoints for managing 7 event types (quarterly results, AGM, EGM,
dividend, split, bonus, rights) and their reminder subscriptions.
"""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.corporate_reminder_service import CorporateReminderService
from titan_x.services.notification_service import NotificationService
from titan_x.core.config import get_settings

router = APIRouter(prefix="/corporate-reminders", tags=["corporate_reminders"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> CorporateReminderService:
    notify = NotificationService(session, get_settings())
    return CorporateReminderService(session, notify)


# ── Event Registration ───────────────────────────────────────────────────────


@router.post("/events/quarterly", summary="Register quarterly results board meeting")
async def create_quarterly(
    symbol: str,
    board_meeting_date: date,
    quarter: int | None = None,
    fiscal_year: int | None = None,
    description: str | None = None,
    source: str | None = None,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.register_quarterly(
        symbol, board_meeting_date, quarter, fiscal_year, description, source,
    )
    return _event_dict(entry)


@router.post("/events/agm", summary="Register Annual General Meeting")
async def create_agm(
    symbol: str,
    meeting_date: date,
    venue: str | None = None,
    chairman: str | None = None,
    resolutions: str | None = None,
    book_closure_start: date | None = None,
    book_closure_end: date | None = None,
    source: str | None = None,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.register_agm(
        symbol, meeting_date, venue, chairman, resolutions,
        book_closure_start, book_closure_end, source,
    )
    return _event_dict(entry)


@router.post("/events/egm", summary="Register Extraordinary General Meeting")
async def create_egm(
    symbol: str,
    meeting_date: date,
    purpose: str | None = None,
    venue: str | None = None,
    source: str | None = None,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.register_egm(symbol, meeting_date, purpose, venue, source)
    return _event_dict(entry)


@router.post("/events/dividend", summary="Register dividend event")
async def create_dividend(
    symbol: str,
    ex_date: date,
    record_date: date | None = None,
    payment_date: date | None = None,
    amount_per_share: float | None = None,
    dividend_type: str | None = None,
    announcement_date: date | None = None,
    source: str | None = None,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.register_dividend(
        symbol, ex_date, record_date, payment_date,
        amount_per_share, dividend_type, announcement_date, source,
    )
    return _event_dict(entry)


@router.post("/events/split", summary="Register stock split")
async def create_split(
    symbol: str,
    ex_date: date,
    record_date: date | None = None,
    old_face_value: float | None = None,
    new_face_value: float | None = None,
    ratio_numerator: int | None = None,
    ratio_denominator: int | None = None,
    source: str | None = None,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.register_split(
        symbol, ex_date, record_date, old_face_value, new_face_value,
        ratio_numerator, ratio_denominator, source,
    )
    return _event_dict(entry)


@router.post("/events/bonus", summary="Register bonus issue")
async def create_bonus(
    symbol: str,
    ex_date: date,
    record_date: date | None = None,
    ratio_numerator: int = 1,
    ratio_denominator: int = 1,
    source: str | None = None,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.register_bonus(
        symbol, ex_date, record_date, ratio_numerator, ratio_denominator, source,
    )
    return _event_dict(entry)


@router.post("/events/rights", summary="Register rights issue")
async def create_rights(
    symbol: str,
    ex_date: date,
    record_date: date | None = None,
    entitlement_ratio_numerator: int = 1,
    entitlement_ratio_denominator: int = 1,
    issue_price: float | None = None,
    premium: float | None = None,
    source: str | None = None,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.register_rights(
        symbol, ex_date, record_date,
        entitlement_ratio_numerator, entitlement_ratio_denominator,
        issue_price, premium, source,
    )
    return _event_dict(entry)


@router.post("/events", summary="Register a generic corporate event")
async def create_event(
    symbol: str,
    event_type: str,
    announcement_date: date | None = None,
    record_date: date | None = None,
    ex_date: date | None = None,
    payment_date: date | None = None,
    board_meeting_date: date | None = None,
    meeting_date: date | None = None,
    description: str | None = None,
    details_json: str | None = None,
    source: str | None = None,
    is_confirmed: bool = False,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        entry = await service.register_event(
            symbol, event_type, announcement_date, record_date,
            ex_date, payment_date, board_meeting_date, meeting_date,
            description, details_json, source, is_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _event_dict(entry)


# ── Event Queries ────────────────────────────────────────────────────────────


@router.get("/events")
async def list_events(
    symbol: str | None = None,
    event_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    confirmed_only: bool = False,
    service: CorporateReminderService = Depends(_get_service),
) -> list[dict[str, Any]]:
    entries = await service.list_events(symbol, event_type, from_date, to_date, confirmed_only)
    return [_event_dict(e) for e in entries]


@router.get("/events/{event_id}")
async def get_event(
    event_id: int,
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    entry = await service.get_event(event_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_dict(entry)


# ── Reminder Subscriptions ───────────────────────────────────────────────────


@router.post("/subscribe/{event_id}")
async def subscribe(
    event_id: int,
    days_before: int = Query(7, ge=1, le=90),
    current_user: User = Depends(deps.get_current_active_user),
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        reminder = await service.subscribe(current_user.id, event_id, days_before)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _reminder_dict(reminder)


@router.post("/subscribe/bulk")
async def subscribe_bulk(
    event_ids: list[int],
    days_before: int = Query(7, ge=1, le=90),
    current_user: User = Depends(deps.get_current_active_user),
    service: CorporateReminderService = Depends(_get_service),
) -> list[dict[str, Any]]:
    reminders = await service.subscribe_multi(current_user.id, event_ids, days_before)
    return [_reminder_dict(r) for r in reminders]


@router.delete("/subscribe/{reminder_id}")
async def unsubscribe(
    reminder_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    deleted = await service.unsubscribe(reminder_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"deleted": True}


@router.get("/my")
async def my_reminders(
    status: str | None = None,
    current_user: User = Depends(deps.get_current_active_user),
    service: CorporateReminderService = Depends(_get_service),
) -> list[dict[str, Any]]:
    reminders = await service.get_user_reminders(current_user.id, status)
    return [_reminder_dict(r) for r in reminders]


@router.post("/{reminder_id}/acknowledge")
async def acknowledge(
    reminder_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    ok = await service.acknowledge(reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"acknowledged": True}


# ── Admin ────────────────────────────────────────────────────────────────────


@router.post("/generate")
async def generate_reminders(
    current_user: User = Depends(deps.get_current_active_superuser),
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.generate_reminders()


@router.get("/stats")
async def reminder_stats(
    current_user: User = Depends(deps.get_current_active_superuser),
    service: CorporateReminderService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.get_reminder_stats()


# ── Serialisers ──────────────────────────────────────────────────────────────


def _event_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "symbol": e.symbol,
        "event_type": e.event_type,
        "announcement_date": e.announcement_date.isoformat() if e.announcement_date else None,
        "record_date": e.record_date.isoformat() if e.record_date else None,
        "ex_date": e.ex_date.isoformat() if e.ex_date else None,
        "payment_date": e.payment_date.isoformat() if e.payment_date else None,
        "description": e.description,
        "details_json": e.details_json,
        "is_confirmed": e.is_confirmed,
        "source": e.source,
    }


def _reminder_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "event_id": r.event_id,
        "event_type": r.event_type,
        "symbol": r.symbol,
        "days_before": r.days_before,
        "reminder_date": r.reminder_date.isoformat(),
        "status": r.status,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "notification_id": r.notification_id,
    }
