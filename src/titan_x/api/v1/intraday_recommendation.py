from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from titan_x.api import deps
from titan_x.models.company import Company
from titan_x.models.user import User
from titan_x.services.intraday_recommendation_service import get_intraday_recommendations
from titan_x.services.strict_recommendation_service import get_strict_recommendations

router = APIRouter(tags=["intraday-recommendations"])


@router.get("/recommendations/intraday")
async def intraday_recommendations(
    segment: str = Query(default="equity", pattern=r"^(equity|fno)$"),
    limit: int = Query(default=100, ge=1, le=3000),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    """Return live 5-minute intraday opportunities.

    Equity uses the active NSE/BSE company universe stored in Titan X instead
    of the old hard-coded 30-symbol slice. F&O keeps its dedicated derivatives
    universe plus major indices. ``limit`` controls returned actionable
    signals, not the size of the equity database universe.
    """
    try:
        universe_symbols: list[str] | None = None
        if segment == "equity":
            rows = (
                await session.execute(
                    select(Company.symbol)
                    .where(Company.status == "active")
                    .where(Company.exchange.in_(["NSE", "BSE"]))
                    .order_by(Company.symbol.asc())
                    .limit(3000)
                )
            ).all()
            universe_symbols = [str(row[0]).upper() for row in rows if row[0]]

        return await get_intraday_recommendations(
            segment=segment,
            limit=limit,
            universe_symbols=universe_symbols,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Intraday market data unavailable: {exc}") from exc


@router.get("/recommendations/strict")
async def strict_recommendations(
    mode: str = Query(default="delivery", pattern=r"^(delivery|intraday)$"),
    segment: str = Query(default="equity", pattern=r"^(equity|fno)$"),
    limit: int = Query(default=100, ge=1, le=3000),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_user),
):
    """Return only recommendations passing the actual Technical Pillar >=95 gate.

    Delivery mode requires the same stock to have Technical Pillar Score >=95
    on both the daily/delivery model and the live 5-minute intraday model.
    Intraday mode applies the same >=95 Technical Pillar Score gate directly
    to the live 5-minute model. Confidence and directional conviction are not
    used for the strict threshold.
    """
    try:
        return await get_strict_recommendations(
            session=session,
            mode=mode,
            segment=segment,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Strict recommendation scan unavailable: {exc}") from exc
