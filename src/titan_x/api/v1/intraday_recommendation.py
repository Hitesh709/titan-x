from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from titan_x.api import deps
from titan_x.api.deps import get_app_session_factory
from titan_x.models.company import Company
from titan_x.models.user import User
from titan_x.services.jugaad_intraday_recommendation_service import get_intraday_recommendations
from titan_x.services.strict_recommendation_service import get_strict_recommendations, get_strict_scan_status

router = APIRouter(tags=["intraday-recommendations"])


@router.get("/recommendations/intraday")
async def intraday_recommendations(
    segment: str = Query(default="equity", pattern=r"^(equity|fno)$"),
    limit: int = Query(default=100, ge=1, le=100),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    """Return live 5-minute intraday opportunities from the configured NSE feed."""
    try:
        universe_symbols: list[str] | None = None
        if segment == "equity":
            rows = (
                await session.execute(
                    select(Company.symbol)
                    .where(Company.status == "active")
                    .where(Company.exchange.in_(["NSE", "BSE"]))
                    .order_by(Company.symbol.asc())
                    .limit(100)
                )
            ).all()
            universe_symbols = [str(row[0]).upper() for row in rows if row[0]]

        return await get_intraday_recommendations(segment=segment, limit=limit, universe_symbols=universe_symbols)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Intraday market data unavailable: {exc}") from exc


@router.get("/recommendations/strict")
async def strict_recommendations(
    mode: str = Query(default="delivery", pattern=r"^(delivery|intraday)$"),
    segment: str = Query(default="equity", pattern=r"^(equity|fno)$"),
    limit: int = Query(default=100, ge=1, le=100),
    session_factory=Depends(get_app_session_factory),
    _: User = Depends(deps.get_current_active_user),
):
    """Start/return a non-blocking strict scan."""
    try:
        return await get_strict_recommendations(session_factory=session_factory, mode=mode, segment=segment, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Strict recommendation scan unavailable: {exc}") from exc


@router.get("/recommendations/strict/status")
async def strict_scan_status(
    mode: str = Query(default="delivery", pattern=r"^(delivery|intraday)$"),
    segment: str = Query(default="equity", pattern=r"^(equity|fno)$"),
    _: User = Depends(deps.get_current_active_user),
):
    """Return progress for the background strict scan."""
    return get_strict_scan_status(mode, segment)
