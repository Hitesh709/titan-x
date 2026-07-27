from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.regime_detection_service import RegimeDetectionService

router = APIRouter(prefix="/regime-detection", tags=["regime-detection"])


@router.post("/detect/{symbol}")
async def detect_regime(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RegimeDetectionService(db)
    result = await svc.detect_regime(symbol.upper(), as_of_date)
    return {
        "id": result.id,
        "symbol": result.symbol,
        "as_of_date": result.as_of_date.isoformat(),
        "trend_regime": result.trend_regime,
        "volatility_regime": result.volatility_regime,
        "sentiment_regime": result.sentiment_regime,
        "trend_score": result.trend_score,
        "volatility_score": result.volatility_score,
        "sentiment_score": result.sentiment_score,
        "confidence": result.confidence,
        "momentum_20d": result.momentum_20d,
        "momentum_50d": result.momentum_50d,
        "price_vs_sma_200_pct": result.price_vs_sma_200_pct,
        "volatility_20d": result.volatility_20d,
    }


@router.get("/detect/{symbol}")
async def get_regime(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RegimeDetectionService(db)
    result = await svc.get_regime(symbol.upper(), as_of_date)
    if not result:
        raise HTTPException(404, "Regime not found")
    return result


@router.get("/detect/{symbol}/history")
async def list_regimes(
    symbol: str,
    limit: int = Query(30, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RegimeDetectionService(db)
    return await svc.list_regimes(symbol.upper(), limit=limit, offset=offset)


@router.post("/signal/{symbol}")
async def generate_signal(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RegimeDetectionService(db)
    result = await svc.generate_signal(symbol.upper(), as_of_date)
    return {
        "id": result.id,
        "symbol": result.symbol,
        "as_of_date": result.as_of_date.isoformat(),
        "signal": result.signal,
        "confidence": result.confidence,
        "regime_summary": result.regime_summary,
        "supporting_factors": result.supporting_factors,
        "expiry_date": result.expiry_date.isoformat() if result.expiry_date else None,
    }


@router.get("/signal/{symbol}")
async def get_signal(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RegimeDetectionService(db)
    result = await svc.get_signal(symbol.upper(), as_of_date)
    if not result:
        raise HTTPException(404, "Signal not found")
    return result


@router.get("/signal/{symbol}/history")
async def list_signals(
    symbol: str,
    limit: int = Query(30, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = RegimeDetectionService(db)
    return await svc.list_signals(symbol.upper(), limit=limit, offset=offset)
