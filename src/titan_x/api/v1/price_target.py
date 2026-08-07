from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.price_target_service import PriceTargetService

router = APIRouter(prefix="/price-targets", tags=["price_targets"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> PriceTargetService:
    return PriceTargetService(session)


def _pt_dict(pt: Any) -> dict[str, Any]:
    return {
        "id": pt.id,
        "symbol": pt.symbol,
        "trade_date": pt.trade_date.isoformat() if pt.trade_date else None,
        "direction": pt.direction,
        "entry_price": pt.entry_price,
        "current_price": pt.current_price,
        "target_1": {
            "price": pt.target_1_price,
            "pct": pt.target_1_pct,
            "probability": pt.target_1_probability,
        },
        "target_2": {
            "price": pt.target_2_price,
            "pct": pt.target_2_pct,
            "probability": pt.target_2_probability,
        },
        "target_3": {
            "price": pt.target_3_price,
            "pct": pt.target_3_pct,
            "probability": pt.target_3_probability,
        },
        "expected_holding_days": pt.expected_holding_days,
        "method": pt.method,
        "atr_value": pt.atr_value,
        "nearest_resistance": pt.nearest_resistance,
        "volatility_20d": pt.volatility_20d,
        "is_active": pt.is_active,
    }


@router.post("/generate/{symbol}", summary="Generate price targets for a symbol")
async def generate(
    symbol: str,
    direction: str = Query("bullish"),
    entry_price: float | None = Query(None),
    service: PriceTargetService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    result = await service.generate(
        symbol=symbol, direction=direction, entry_price=entry_price,
    )
    return {"price_target": _pt_dict(result)}


@router.get("/targets/{symbol}", summary="Get price target history for a symbol")
async def get_targets(
    symbol: str,
    limit: int = Query(20),
    offset: int = Query(0),
    service: PriceTargetService = Depends(_get_service),
) -> dict[str, Any]:
    targets = await service.get_targets(symbol, limit=limit, offset=offset)
    return {"total": len(targets), "targets": [_pt_dict(pt) for pt in targets]}


@router.get("/{target_id}", summary="Get a specific price target")
async def get_target(
    target_id: int,
    service: PriceTargetService = Depends(_get_service),
) -> dict[str, Any]:
    pt = await service.get_target(target_id)
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price target not found")
    return {"price_target": _pt_dict(pt)}
