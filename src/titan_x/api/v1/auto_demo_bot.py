from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.auto_demo_bot_engine import AutoDemoBotEngine

router = APIRouter(prefix="/auto-demo-bot", tags=["auto-demo-bot"])


@router.post("/run")
async def run_demo_bot(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    trade_amount: float = Query(10000.0, gt=0, le=10000000),
    profile_ratio: float = Query(1.0, gt=0, le=20),
) -> dict:
    try:
        result = await AutoDemoBotEngine(session).run_once(current_user.id, trade_amount, profile_ratio)
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Auto demo bot run failed: {type(exc).__name__}") from exc


# Compatibility endpoint for older clients. It no longer has a finite cycle limit.
@router.post("/cycle")
async def run_demo_cycle_compat(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
    symbol: str = Query("", max_length=20),
    cycle: int | None = Query(None, ge=1),
    trade_amount: float = Query(10000.0, gt=0, le=10000000),
) -> dict:
    try:
        result = await AutoDemoBotEngine(session).run_once(current_user.id, trade_amount, 1.0)
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Auto demo bot run failed: {type(exc).__name__}") from exc


@router.get("/status")
async def demo_bot_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(request_session)],
) -> dict:
    account = await AutoDemoBotEngine(session).paper.get_account(current_user.id)
    return {
        "enabled": True,
        "mode": "paper_demo",
        "continuous": True,
        "strategy_window": "3h",
        "stop_loss_max_pct": 40,
        "max_trades_per_burst": 50,
        "paper_account": account is not None,
    }
