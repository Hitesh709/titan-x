from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.macro_service import MacroService

router = APIRouter(prefix="/macro", tags=["macro"])


class IndicatorCreate(BaseModel):
    indicator_type: str
    as_of_date: date
    value: float
    unit: str | None = None
    source: str | None = None
    description: str | None = None


@router.post("/indicators")
async def create_indicator(body: IndicatorCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = MacroService(db)
    result = await svc.record_indicator(body.indicator_type, body.as_of_date, body.value, body.unit, body.source, body.description)
    return result


@router.get("/indicators")
async def list_indicators(
    indicator_type: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MacroService(db)
    return await svc.list_indicators(indicator_type, limit, offset)


@router.get("/indicators/{indicator_type}/latest")
async def get_latest_indicator(indicator_type: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    svc = MacroService(db)
    result = await svc.get_indicator(indicator_type)
    if not result:
        raise HTTPException(404, f"No {indicator_type} data found")
    return result


@router.post("/analyze")
async def analyze_macro(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MacroService(db)
    result = await svc.analyze(as_of_date)
    return {
        "id": result.id,
        "as_of_date": result.as_of_date.isoformat(),
        "interest_rate_score": result.interest_rate_score,
        "inflation_score": result.inflation_score,
        "gdp_score": result.gdp_score,
        "currency_score": result.currency_score,
        "bond_yield_score": result.bond_yield_score,
        "oil_score": result.oil_score,
        "gold_score": result.gold_score,
        "composite_macro_score": result.composite_macro_score,
        "macro_regime": result.macro_regime,
        "growth_inflation_regime": result.growth_inflation_regime,
        "risk_regime": result.risk_regime,
    }


@router.get("/analyze")
async def get_analysis(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MacroService(db)
    result = await svc.get_analysis(as_of_date)
    if not result:
        raise HTTPException(404, "Analysis not found")
    return result


@router.get("/analyze/history")
async def list_analyses(
    limit: int = Query(30, le=100), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MacroService(db)
    return await svc.list_analyses(limit, offset)


@router.post("/features")
async def generate_features(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MacroService(db)
    results = await svc.generate_features(as_of_date)
    return [
        {"id": f.id, "feature_name": f.feature_name, "value": f.value, "category": f.category}
        for f in results
    ]


@router.get("/features")
async def get_features(
    feature_name: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MacroService(db)
    return await svc.get_features(feature_name, category, limit)
