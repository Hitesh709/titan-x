from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.api import deps
from titan_x.models.prediction_audit import PredictionAudit

router = APIRouter(prefix="/prediction-audit", tags=["prediction_audit"])


@router.get("/{prediction_id}", summary="Get the provenance and outcomes for a prediction")
async def get_prediction_audit(
    prediction_id: int,
    session: AsyncSession = Depends(deps.request_session),
    _current_user: Any = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    audit = await session.scalar(
        select(PredictionAudit)
        .options(selectinload(PredictionAudit.outcomes))
        .where(PredictionAudit.prediction_id == prediction_id)
    )
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction audit not found")

    return {
        "prediction_id": audit.prediction_id,
        "recommendation_id": audit.recommendation_id,
        "symbol": audit.symbol,
        "as_of_date": audit.as_of_date.isoformat(),
        "generated_at": audit.generated_at.isoformat(),
        "data_snapshot_ref": audit.data_snapshot_ref,
        "data_source_ref": audit.data_source_ref,
        "feature_version_ref": audit.feature_version_ref,
        "model_version_ref": audit.model_version_ref,
        "market_regime": audit.market_regime,
        "input_hash": audit.input_hash,
        "explanation_hash": audit.explanation_hash,
        "audit_schema_version": audit.audit_schema_version,
        "outcomes": [
            {
                "horizon_days": outcome.horizon_days,
                "observation_date": outcome.observation_date.isoformat() if outcome.observation_date else None,
                "entry_price": outcome.entry_price,
                "close_price": outcome.close_price,
                "close_return_pct": outcome.close_return_pct,
                "max_favorable_excursion_pct": outcome.max_favorable_excursion_pct,
                "max_adverse_excursion_pct": outcome.max_adverse_excursion_pct,
                "target_hit": outcome.target_hit,
                "stop_hit": outcome.stop_hit,
                "direction_correct": outcome.direction_correct,
                "resolution_status": outcome.resolution_status,
                "resolved_at": outcome.resolved_at.isoformat() if outcome.resolved_at else None,
            }
            for outcome in sorted(audit.outcomes, key=lambda item: item.horizon_days)
        ],
    }


@router.get("", summary="List audited predictions for a symbol")
async def list_prediction_audits(
    symbol: str = Query(..., min_length=1, max_length=20),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(deps.request_session),
    _current_user: Any = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    result = await session.execute(
        select(PredictionAudit)
        .options(selectinload(PredictionAudit.outcomes))
        .where(PredictionAudit.symbol == symbol.upper())
        .order_by(PredictionAudit.generated_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    return {
        "symbol": symbol.upper(),
        "total": len(rows),
        "audits": [
            {
                "prediction_id": row.prediction_id,
                "as_of_date": row.as_of_date.isoformat(),
                "generated_at": row.generated_at.isoformat(),
                "model_version_ref": row.model_version_ref,
                "market_regime": row.market_regime,
                "input_hash": row.input_hash,
                "outcome_count": len(row.outcomes),
            }
            for row in rows
        ],
    }
