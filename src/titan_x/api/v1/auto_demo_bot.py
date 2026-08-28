from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.auto_demo_bot_engine import AutoDemoBotEngine

router = APIRouter(prefix="/auto-demo-bot", tags=["auto-demo-bot"])


@router.post("/cycle")
async def run_demo_cycle(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    symbol: str = Query("RELIANCE", min_length=1, max_length=20),
    cycle: int = Query(..., ge=1, le=15),
    trade_amount: float = Query(10000.0, gt=0, le=100000),
) -> dict:
    try:
        result = await AutoDemoBotEngine(session).run_cycle(current_user.id, symbol, cycle, trade_amount)
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Auto demo bot cycle failed: {type(exc).__name__}")


@router.get("/status")
async def demo_bot_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    account = await AutoDemoBotEngine(session).paper.get_account(current_user.id)
    return {"enabled": True, "mode": "paper_demo", "max_minutes": 15, "paper_account": account is not None}
