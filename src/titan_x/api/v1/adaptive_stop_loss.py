from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.adaptive_stop_loss_service import AdaptiveStopLossService

router = APIRouter(prefix="/adaptive-stop-loss", tags=["adaptive_stop_loss"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> AdaptiveStopLossService:
    return AdaptiveStopLossService(session)


def _sl_dict(sl: Any) -> dict[str, Any]:
    return {
        "id": sl.id,
        "symbol": sl.symbol,
        "trade_date": sl.trade_date.isoformat() if sl.trade_date else None,
        "entry_price": sl.entry_price,
        "current_price": sl.current_price,
        "atr_value": sl.atr_value,
        "atr_multiplier": sl.atr_multiplier,
        "sl_price_atr": sl.sl_price_atr,
        "sl_pct_atr": sl.sl_pct_atr,
        "nearest_support": sl.nearest_support,
        "support_strength": sl.support_strength,
        "sl_price_support": sl.sl_price_support,
        "sl_pct_support": sl.sl_pct_support,
        "volatility_20d": sl.volatility_20d,
        "vol_multiplier": sl.vol_multiplier,
        "sl_price_volatility": sl.sl_price_volatility,
        "sl_pct_volatility": sl.sl_pct_volatility,
        "trend_regime": sl.trend_regime,
        "volatility_regime": sl.volatility_regime,
        "regime_adjustment": sl.regime_adjustment,
        "liquidity_score": sl.liquidity_score,
        "liquidity_rating": sl.liquidity_rating,
        "liq_adjustment": sl.liq_adjustment,
        "composite_stop_price": sl.composite_stop_price,
        "composite_stop_pct": sl.composite_stop_pct,
        "method": sl.method,
        "is_trailing": sl.is_trailing,
        "is_active": sl.is_active,
    }


@router.post("/compute/{symbol}", summary="Compute adaptive stop loss for a symbol")
async def compute(
    symbol: str,
    entry_price: float | None = Query(None),
    atr_multiplier: float = Query(2.0),
    vol_multiplier: float = Query(1.5),
    trailing_activation_pct: float | None = Query(5.0),
    service: AdaptiveStopLossService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    result = await service.compute(
        symbol=symbol,
        entry_price=entry_price,
        atr_multiplier=atr_multiplier,
        vol_multiplier=vol_multiplier,
        trailing_activation_pct=trailing_activation_pct,
    )
    return {"stop_loss": _sl_dict(result)}


@router.get("/levels/{symbol}", summary="Get stop loss history for a symbol")
async def get_levels(
    symbol: str,
    limit: int = Query(20),
    offset: int = Query(0),
    service: AdaptiveStopLossService = Depends(_get_service),
) -> dict[str, Any]:
    levels = await service.get_levels(symbol, limit=limit, offset=offset)
    return {"total": len(levels), "levels": [_sl_dict(sl) for sl in levels]}


@router.get("/active/{symbol}", summary="Get active stop loss for a symbol")
async def get_active(
    symbol: str,
    service: AdaptiveStopLossService = Depends(_get_service),
) -> dict[str, Any]:
    sl = await service.get_active(symbol)
    if not sl:
        return {"stop_loss": None}
    return {"stop_loss": _sl_dict(sl)}


@router.post("/{stop_loss_id}/deactivate", summary="Deactivate a stop loss level")
async def deactivate(
    stop_loss_id: int,
    service: AdaptiveStopLossService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> dict[str, Any]:
    sl = await service.deactivate(stop_loss_id)
    if not sl:
        return {"error": "Stop loss not found"}
    return {"stop_loss": _sl_dict(sl)}
