from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.nightly_evaluation_service import NightlyEvaluationService

router = APIRouter(prefix="/nightly-evaluation", tags=["nightly_evaluation"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> NightlyEvaluationService:
    return NightlyEvaluationService(session)


def _eval_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "evaluation_date": e.evaluation_date.isoformat() if e.evaluation_date else None,
        "period_start": e.period_start.isoformat() if e.period_start else None,
        "period_end": e.period_end.isoformat() if e.period_end else None,
        "status": e.status,
        "total_predictions": e.total_predictions,
        "correct_predictions": e.correct_predictions,
        "incorrect_predictions": e.incorrect_predictions,
        "accuracy": e.accuracy,
        "mae": e.mae,
        "rmse": e.rmse,
        "bias_score": e.bias_score,
        "bias_direction": e.bias_direction,
        "failure_count": e.failure_count,
        "weight_adjustments_json": e.weight_adjustments_json,
        "summary_json": e.summary_json,
    }


@router.post("/run", summary="Run a nightly evaluation")
async def run_evaluation(
    evaluation_date: date | None = Query(None),
    lookback_days: int = Query(30),
    failure_threshold_pct: float = Query(10.0),
    service: NightlyEvaluationService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    result = await service.run_evaluation(
        evaluation_date=evaluation_date,
        lookback_days=lookback_days,
        failure_threshold_pct=failure_threshold_pct,
    )
    return {"evaluation": _eval_dict(result)}


@router.get("/latest", summary="Get latest completed evaluation")
async def get_latest(
    service: NightlyEvaluationService = Depends(_get_service),
):
    ev = await service.get_latest_evaluation()
    if not ev:
        raise HTTPException(status_code=404, detail="No completed evaluation found")
    return {"evaluation": _eval_dict(ev)}


@router.get("/list", summary="List evaluations")
async def list_evaluations(
    limit: int = Query(20),
    offset: int = Query(0),
    service: NightlyEvaluationService = Depends(_get_service),
):
    evals = await service.get_evaluations(limit=limit, offset=offset)
    return {"total": await service.count_evaluations(), "evaluations": [_eval_dict(e) for e in evals]}


@router.get("/{evaluation_id:int}", summary="Get an evaluation by id")
async def get_evaluation(
    evaluation_id: int,
    service: NightlyEvaluationService = Depends(_get_service),
):
    ev = await service.get_evaluation(evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return {"evaluation": _eval_dict(ev)}


@router.get("/{evaluation_id:int}/errors", summary="Get prediction errors for an evaluation")
async def get_errors(
    evaluation_id: int,
    is_failure: bool | None = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
    service: NightlyEvaluationService = Depends(_get_service),
):
    errors = await service.get_errors(
        evaluation_id=evaluation_id, is_failure=is_failure,
        limit=limit, offset=offset,
    )
    return {"total": await service.count_errors(evaluation_id, is_failure), "errors": [_error_dict(e) for e in errors]}


@router.get("/{evaluation_id:int}/failures", summary="Get failures for an evaluation")
async def get_failures(
    evaluation_id: int,
    limit: int = Query(100),
    offset: int = Query(0),
    service: NightlyEvaluationService = Depends(_get_service),
):
    failures = await service.get_failures(
        evaluation_id=evaluation_id, limit=limit, offset=offset,
    )
    return {"total": await service.count_errors(evaluation_id, is_failure=True), "failures": [_error_dict(e) for e in failures]}


@router.get("/trend", summary="Get evaluation trend")
async def get_trend(
    limit: int = Query(30),
    service: NightlyEvaluationService = Depends(_get_service),
):
    trend = await service.get_trend(limit=limit)
    return {"trend": trend}


def _error_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "symbol": e.symbol,
        "as_of_date": e.as_of_date.isoformat() if e.as_of_date else None,
        "horizon": e.horizon,
        "signal": e.signal,
        "predicted_return_pct": e.predicted_return_pct,
        "actual_return_pct": e.actual_return_pct,
        "error_pct": e.error_pct,
        "abs_error_pct": e.abs_error_pct,
        "predicted_direction": e.predicted_direction,
        "actual_direction": e.actual_direction,
        "was_correct": e.was_correct,
        "is_failure": e.is_failure,
        "confidence": e.confidence,
    }
