from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.api.schemas import PaginatedResponse
from titan_x.services.model_evaluation_service import ModelEvaluationService

router = APIRouter(tags=["model-evaluation"])


@router.post("/evaluate", status_code=201)
async def run_evaluation(
    y_true: str = Query(...),
    y_pred: str = Query(...),
    y_prob: str | None = None,
    returns: str | None = None,
    threshold: float = 0.5,
    experiment_id: int | None = None,
    model_registry_entry_id: int | None = None,
    model_registry_version_id: int | None = None,
    name: str | None = None,
    dataset_name: str | None = None,
    notes: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = ModelEvaluationService(session)
    eval_record = await svc.run_evaluation(
        y_true=_parse_float_list(y_true),
        y_pred=_parse_float_list(y_pred),
        y_prob=_parse_float_list(y_prob) if y_prob else None,
        returns=_parse_float_list(returns) if returns else None,
        threshold=threshold,
        experiment_id=experiment_id,
        model_registry_entry_id=model_registry_entry_id,
        model_registry_version_id=model_registry_version_id,
        name=name, dataset_name=dataset_name, notes=notes,
        metadata=_parse_json(metadata),
    )
    metrics = await svc.get_evaluation_metrics(eval_record.id)
    return {
        "id": eval_record.id,
        "name": eval_record.name,
        "status": eval_record.status,
        "num_samples": eval_record.num_samples,
        "dataset_name": eval_record.dataset_name,
        "evaluated_at": eval_record.evaluated_at.isoformat() if eval_record.evaluated_at else None,
        "metrics": {m.metric_name: m.metric_value for m in metrics},
    }


@router.get("/evaluations/{evaluation_id}")
async def get_evaluation(
    evaluation_id: int,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = ModelEvaluationService(session)
    ev = await svc.get_evaluation(evaluation_id)
    if not ev:
        raise HTTPException(404, "Evaluation not found")
    metrics = await svc.get_evaluation_metrics(evaluation_id)
    return _eval_dict(ev, metrics)


@router.get("/evaluations")
async def list_evaluations(
    model_registry_entry_id: int | None = None,
    experiment_id: int | None = None,
    status: str | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = ModelEvaluationService(session)
    items = await svc.list_evaluations(
        model_registry_entry_id=model_registry_entry_id,
        experiment_id=experiment_id, status=status,
        limit=limit, offset=offset,
    )
    result = []
    for ev in items:
        metrics = await svc.get_evaluation_metrics(ev.id)
        result.append(_eval_dict(ev, metrics))
    total = await svc.count_evaluations(
        model_registry_entry_id=model_registry_entry_id,
        experiment_id=experiment_id, status=status,
    )
    return PaginatedResponse(items=result, total=total, limit=limit, skip=offset)


@router.get("/evaluations/{evaluation_id}/metrics")
async def get_evaluation_metrics(
    evaluation_id: int,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = ModelEvaluationService(session)
    items = await svc.get_evaluation_metrics(evaluation_id)
    return {"evaluation_id": evaluation_id, "metrics": {m.metric_name: m.metric_value for m in items}}


@router.get("/metrics/{metric_name}/history")
async def get_metric_history(
    metric_name: str,
    model_registry_entry_id: int | None = None,
    experiment_id: int | None = None,
    limit: int = 100,
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = ModelEvaluationService(session)
    history = await svc.get_metric_history(
        metric_name=metric_name,
        model_registry_entry_id=model_registry_entry_id,
        experiment_id=experiment_id, limit=limit,
    )
    return {"metric_name": metric_name, "history": history}


@router.post("/evaluations/compare")
async def compare_evaluations(
    evaluation_ids: str = Query(...),
    session=Depends(deps.get_session),
    _=Depends(deps.get_current_active_superuser),
):
    svc = ModelEvaluationService(session)
    eids = [int(x) for x in evaluation_ids.split(",")]
    result = await svc.compare_evaluations(eids)
    return result


def _parse_float_list(val: str) -> list[float]:
    return [float(x.strip()) for x in val.split(",") if x.strip()]


def _parse_json(val: str | None) -> Any:
    if val is None:
        return None
    import json as _json
    return _json.loads(val)


def _eval_dict(ev: Any, metrics: list) -> dict:
    return {
        "id": ev.id,
        "name": ev.name,
        "experiment_id": ev.experiment_id,
        "model_registry_entry_id": ev.model_registry_entry_id,
        "status": ev.status,
        "dataset_name": ev.dataset_name,
        "num_samples": ev.num_samples,
        "duration_seconds": ev.duration_seconds,
        "notes": ev.notes,
        "evaluated_at": ev.evaluated_at.isoformat() if ev.evaluated_at else None,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
        "metrics": {m.metric_name: m.metric_value for m in metrics},
    }
