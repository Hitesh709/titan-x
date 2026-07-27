from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, get_db
from titan_x.models.user import User
from titan_x.services.master_decision_service import MasterDecisionService

router = APIRouter(prefix="/master-decision", tags=["master-decision"])


@router.post("/evaluate/{symbol}")
async def evaluate_symbol(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MasterDecisionService(db)
    result = await svc.evaluate(symbol.upper(), as_of_date)
    return {
        "id": result.id,
        "symbol": result.symbol,
        "as_of_date": result.as_of_date.isoformat(),
        "final_ai_score": result.final_ai_score,
        "confidence": result.confidence,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level,
        "recommendation": result.recommendation,
        "is_weak": result.is_weak,
        "rejection_reason": result.rejection_reason,
        "engine_count": result.engine_count,
        "decision_summary": result.decision_summary,
    }


@router.post("/evaluate-all")
async def evaluate_all(
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MasterDecisionService(db)
    results = await svc.evaluate_all(as_of_date)
    return {
        "total": len(results),
        "decisions": [
            {
                "symbol": d.symbol,
                "final_ai_score": d.final_ai_score,
                "confidence": d.confidence,
                "risk_level": d.risk_level,
                "recommendation": d.recommendation,
                "is_weak": d.is_weak,
                "rejection_reason": d.rejection_reason,
                "engine_count": d.engine_count,
                "decision_summary": d.decision_summary,
            }
            for d in results
        ],
    }


@router.get("/decisions")
async def list_decisions(
    symbol: str | None = Query(None),
    min_score: float | None = Query(None, ge=0, le=100),
    recommendation: str | None = Query(None, pattern="^(strong_buy|buy|hold|sell|strong_sell)$"),
    include_weak: bool = Query(False),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MasterDecisionService(db)
    return await svc.list_decisions(symbol, min_score, recommendation, include_weak, limit, offset)


@router.get("/decisions/{symbol}")
async def get_decision(
    symbol: str,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    svc = MasterDecisionService(db)
    result = await svc.get_decision(symbol.upper(), as_of_date)
    if not result:
        raise HTTPException(404, "Decision not found")
    return {
        "id": result.id,
        "symbol": result.symbol,
        "as_of_date": result.as_of_date.isoformat(),
        "final_ai_score": result.final_ai_score,
        "confidence": result.confidence,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level,
        "recommendation": result.recommendation,
        "is_weak": result.is_weak,
        "rejection_reason": result.rejection_reason,
        "engine_count": result.engine_count,
        "financial_analysis_score": result.financial_analysis_score,
        "corporate_governance_score": result.corporate_governance_score,
        "institutional_score": result.institutional_score,
        "valuation_score": result.valuation_score,
        "momentum_score": result.momentum_score,
        "liquidity_score": result.liquidity_score,
        "technical_score": result.technical_score,
        "macro_score": result.macro_score,
        "global_score": result.global_score,
        "pattern_score": result.pattern_score,
        "regime_score": result.regime_score,
        "prediction_score": result.prediction_score,
        "evidence": result.evidence_json,
        "decision_summary": result.decision_summary,
    }
