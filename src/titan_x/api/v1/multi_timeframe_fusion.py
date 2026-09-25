"""Titan X multi-timeframe Fusion confirmation.

Phase 4: evaluate the same deterministic Fusion engine independently on
5m, 15m and 30m candles, then require directional alignment before exposing
an actionable multi-timeframe decision.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import get_current_active_user
from titan_x.services.titan_x_fusion import FusionParams, TitanXFusionEngine
from titan_x.api.v1.fusion import _fetch_candles, _normalize_symbol, _sanitize_reason

router = APIRouter(
    prefix="/fusion-mtf",
    tags=["fusion-multi-timeframe"],
    dependencies=[Depends(get_current_active_user)],
)

_params = FusionParams()
_TIMEFRAMES = ("5m", "15m", "30m")


@router.get("/signal", response_model=dict[str, Any])
async def multi_timeframe_signal(
    symbol: str = Query(..., min_length=1, max_length=16),
) -> dict[str, Any]:
    """Return independent Fusion decisions plus a strict MTF confirmation.

    An actionable BUY requires BUY on all three timeframes; an actionable SELL
    requires SELL on all three. Any disagreement remains HOLD. This avoids
    inventing a score and makes the higher-timeframe filters explicit.
    """
    sym = _normalize_symbol(symbol)
    engine = TitanXFusionEngine(_params)
    results: dict[str, dict[str, Any]] = {}

    for interval in _TIMEFRAMES:
        points = await _fetch_candles(sym, interval=interval)
        if not points or len(points) < _params.min_bars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient candle data for {symbol} on {interval}",
            )
        decision = engine.evaluate(points, dedupe=False, interval=interval)
        results[interval] = {
            "decision": decision["decision"],
            "reason": _sanitize_reason(decision.get("reason", "")),
            "entry": decision.get("entry"),
            "stop_loss": decision.get("stop_loss"),
            "target": decision.get("target"),
            "price": decision.get("price"),
            "regime": decision.get("regime"),
            "gates": decision.get("gates", {}),
        }

    decisions = [results[tf]["decision"] for tf in _TIMEFRAMES]
    aligned_buy = all(value == "BUY" for value in decisions)
    aligned_sell = all(value == "SELL" for value in decisions)

    if aligned_buy:
        final_decision = "BUY"
        final = results["5m"]
        reason = "5m + 15m + 30m Fusion alignment confirmed"
    elif aligned_sell:
        final_decision = "SELL"
        final = results["5m"]
        reason = "5m + 15m + 30m Fusion alignment confirmed"
    else:
        final_decision = "HOLD"
        final = results["5m"]
        reason = "Multi-timeframe directions are not fully aligned"

    return {
        "symbol": sym,
        "decision": final_decision,
        "reason": reason,
        "entry": final.get("entry") if final_decision != "HOLD" else None,
        "stop_loss": final.get("stop_loss") if final_decision != "HOLD" else None,
        "target": final.get("target") if final_decision != "HOLD" else None,
        "price": final.get("price"),
        "regime": final.get("regime"),
        "confirmed": aligned_buy or aligned_sell,
        "timeframes": results,
        "rule": "BUY/SELL only when 5m, 15m and 30m agree; otherwise HOLD",
    }
