from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.trade_journal_service import TradeJournalService

router = APIRouter(prefix="/trade-journal", tags=["trade_journal"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> TradeJournalService:
    return TradeJournalService(session)


def _entry_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "symbol": e.symbol,
        "direction": e.direction,
        "entry_date": e.entry_date.isoformat() if e.entry_date else None,
        "exit_date": e.exit_date.isoformat() if e.exit_date else None,
        "entry_price": e.entry_price,
        "exit_price": e.exit_price,
        "quantity": e.quantity,
        "reason": e.reason,
        "emotion_before": e.emotion_before,
        "emotion_during": e.emotion_during,
        "emotion_after": e.emotion_after,
        "exit_reason": e.exit_reason,
        "exit_analysis": e.exit_analysis,
        "pnl_amount": e.pnl_amount,
        "pnl_pct": e.pnl_pct,
        "lessons_learned": e.lessons_learned,
        "tags": e.tags,
        "setup_type": e.setup_type,
        "mistake": e.mistake,
        "is_closed": e.is_closed,
        "rating": e.rating,
    }


@router.post("/entry/{symbol}", summary="Create a new trade journal entry")
async def create_entry(
    symbol: str,
    direction: str = Query("long"),
    entry_date: datetime = Query(...),
    entry_price: float = Query(...),
    quantity: int = Query(...),
    reason: str | None = Query(None),
    emotion_before: str | None = Query(None),
    setup_type: str | None = Query(None),
    tags: str | None = Query(None),
    service: TradeJournalService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    entry = await service.create_entry(
        user_id=current_user.id,
        symbol=symbol,
        direction=direction,
        entry_date=entry_date,
        entry_price=entry_price,
        quantity=quantity,
        reason=reason,
        emotion_before=emotion_before,
        setup_type=setup_type,
        tags=tags,
    )
    return {"entry": _entry_dict(entry)}


@router.post("/{journal_id}/close", summary="Close a trade journal entry with exit details")
async def close_entry(
    journal_id: int,
    exit_date: datetime = Query(...),
    exit_price: float = Query(...),
    exit_reason: str | None = Query(None),
    exit_analysis: str | None = Query(None),
    emotion_during: str | None = Query(None),
    emotion_after: str | None = Query(None),
    lessons_learned: str | None = Query(None),
    mistake: str | None = Query(None),
    rating: int | None = Query(None),
    service: TradeJournalService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    entry = await service.close_entry(
        journal_id=journal_id,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason=exit_reason,
        exit_analysis=exit_analysis,
        emotion_during=emotion_during,
        emotion_after=emotion_after,
        lessons_learned=lessons_learned,
        mistake=mistake,
        rating=rating,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not your journal entry")
    return {"entry": _entry_dict(entry)}


@router.patch("/{journal_id}", summary="Update a trade journal entry")
async def update_entry(
    journal_id: int,
    body: dict[str, Any],
    service: TradeJournalService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    entry = await service.get_entry(journal_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not your journal entry")

    allowed = {"reason", "emotion_before", "emotion_during", "emotion_after",
               "exit_reason", "exit_analysis", "lessons_learned", "tags",
               "setup_type", "mistake", "screenshot_url", "rating"}
    kwargs = {k: v for k, v in body.items() if k in allowed}
    updated = await service.update_entry(journal_id, **kwargs)
    return {"entry": _entry_dict(updated)} if updated else {"error": "Update failed"}


@router.get("/{journal_id}", summary="Get a trade journal entry")
async def get_entry(
    journal_id: int,
    service: TradeJournalService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    entry = await service.get_entry(journal_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not your journal entry")
    return {"entry": _entry_dict(entry)}


@router.get("/list/{symbol}", summary="List trade journal entries")
async def list_entries(
    symbol: str | None = None,
    is_closed: bool | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    service: TradeJournalService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    entries = await service.get_entries(
        user_id=current_user.id, symbol=symbol,
        is_closed=is_closed, limit=limit, offset=offset,
    )
    return {"total": len(entries), "entries": [_entry_dict(e) for e in entries]}


@router.get("/performance", summary="Get trade performance statistics")
async def get_performance(
    symbol: str | None = Query(None),
    days: int | None = Query(None),
    service: TradeJournalService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_user),
):
    stats = await service.get_performance(
        user_id=current_user.id, symbol=symbol, days=days,
    )
    return {"performance": stats}
