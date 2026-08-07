"""Market Scanner API.

Scan all symbols for breakouts, breakdowns, EMA crossovers,
RSI, MACD, ADX, ATR, and volume signals. View rankings and
scan results.
"""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.market_scanner_service import MarketScannerService

router = APIRouter(prefix="/market-scanner", tags=["market_scanner"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> MarketScannerService:
    return MarketScannerService(session)


# ── Scan ─────────────────────────────────────────────────────────────────────


@router.post("/scan/all", summary="Scan all active symbols")
async def scan_all(
    current_user: User = Depends(deps.get_current_active_superuser),
    service: MarketScannerService = Depends(_get_service),
) -> dict[str, Any]:
    results = await service.scan_all()
    return {
        "scanned": len(results),
        "scan_date": date.today().isoformat(),
    }


@router.post("/scan/{symbol}", summary="Scan a single symbol")
async def scan_symbol(
    symbol: str,
    current_user: User = Depends(deps.get_current_active_user),
    service: MarketScannerService = Depends(_get_service),
) -> dict[str, Any]:
    result = await service.scan_symbol(symbol)
    return _scan_dict(result)


# ── Rankings ─────────────────────────────────────────────────────────────────


@router.get("/rankings", summary="Get ranked scan results")
async def get_rankings(
    scan_date: date | None = None,
    min_score: float = Query(0.0, ge=0, le=100),
    limit: int = Query(100, ge=1, le=500),
    service: MarketScannerService = Depends(_get_service),
) -> list[dict[str, Any]]:
    sd = scan_date
    results = await service.get_rankings(sd, min_score, limit)
    return [_scan_dict(r) for r in results]


@router.get("/rankings/by-signal/{signal}", summary="Get top by signal type")
async def get_top_by_signal(
    signal: str,
    scan_date: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    service: MarketScannerService = Depends(_get_service),
) -> list[dict[str, Any]]:
    valid = {"breakout", "breakdown", "ema_cross", "rsi", "macd", "adx", "atr", "volume"}
    if signal not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid signal '{signal}'. Valid: {', '.join(sorted(valid))}",
        )
    sd = scan_date
    results = await service.get_top_by_signal(signal, sd, limit)
    return [_scan_dict(r) for r in results]


# ── Scan results ─────────────────────────────────────────────────────────────


@router.get("/results/{symbol}", summary="Get latest scan for a symbol")
async def get_latest_scan(
    symbol: str,
    service: MarketScannerService = Depends(_get_service),
) -> dict[str, Any]:
    result = await service.get_latest_scan(symbol)
    if not result:
        raise HTTPException(status_code=404, detail="No scan result found for symbol")
    return _scan_dict(result)


@router.get("/results/{symbol}/history", summary="Get scan history for a symbol")
async def get_scan_history(
    symbol: str,
    limit: int = Query(30, ge=1, le=365),
    service: MarketScannerService = Depends(_get_service),
) -> list[dict[str, Any]]:
    results = await service.get_scan_history(symbol, limit)
    return [_scan_dict(r) for r in results]


# ── Summary ──────────────────────────────────────────────────────────────────


@router.get("/summary", summary="Get scan summary statistics")
async def get_summary(
    scan_date: date | None = None,
    service: MarketScannerService = Depends(_get_service),
) -> dict[str, Any]:
    sd = scan_date
    return await service.get_scan_summary(sd)


@router.get("/dates", summary="Get all scan dates")
async def get_dates(
    service: MarketScannerService = Depends(_get_service),
) -> list[str]:
    dates = await service.get_all_scan_dates()
    return [d.isoformat() for d in dates]


# ── Serialiser ───────────────────────────────────────────────────────────────


def _scan_dict(r: Any) -> dict[str, Any]:
    import json
    signals = {}
    if r.signals_json:
        try:
            signals = json.loads(r.signals_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": r.id,
        "symbol": r.symbol,
        "scan_date": r.scan_date.isoformat(),
        "composite_score": r.composite_score,
        "breakout": {"score": r.breakout_score, "signal": r.breakout_signal, "detail": signals.get("breakout", {})},
        "breakdown": {"score": r.breakdown_score, "signal": r.breakdown_signal, "detail": signals.get("breakdown", {})},
        "ema_cross": {"score": r.ema_cross_score, "signal": r.ema_cross_signal, "detail": signals.get("ema_cross", {})},
        "rsi": {"score": r.rsi_score, "signal": r.rsi_signal, "detail": signals.get("rsi", {})},
        "macd": {"score": r.macd_score, "signal": r.macd_signal, "detail": signals.get("macd", {})},
        "adx": {"score": r.adx_score, "signal": r.adx_signal, "detail": signals.get("adx", {})},
        "atr": {"score": r.atr_score, "signal": r.atr_signal, "detail": signals.get("atr", {})},
        "volume": {"score": r.volume_score, "signal": r.volume_signal, "detail": signals.get("volume", {})},
    }
