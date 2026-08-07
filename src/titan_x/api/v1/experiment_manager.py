from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.api.schemas import PaginatedResponse
from titan_x.services.experiment_manager_service import ExperimentManagerService

router = APIRouter(tags=["experiment-manager"])


# ── Experiments ──

@router.post("/experiments", status_code=201)
async def create_experiment(
    name: str = Query(...),
    description: str | None = None,
    experiment_id: str | None = None,
    metadata: str | None = None,
    tags: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    exp = await svc.create_experiment(
        name=name, description=description,
        experiment_id=experiment_id,
        metadata=_parse_json(metadata),
        tags=_parse_json(tags),
    )
    return {"id": exp.id, "experiment_id": exp.experiment_id, "name": exp.name}


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    exp = await svc.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return _exp_dict(exp)


@router.get("/experiments")
async def list_experiments(
    status: str | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.list_experiments(status=status, limit=limit, offset=offset)
    return PaginatedResponse(items=[_exp_dict(e) for e in items], total=await svc.count_experiments(status), limit=limit, offset=offset)


@router.post("/experiments/{experiment_id}/status")
async def update_status(
    experiment_id: int,
    status: str = Query(...),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    exp = await svc.update_experiment_status(experiment_id, status)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return _exp_dict(exp)


@router.delete("/experiments/{experiment_id}")
async def delete_experiment(
    experiment_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    ok = await svc.delete_experiment(experiment_id)
    if not ok:
        raise HTTPException(404, "Experiment not found")
    return {"deleted": True}


# ── Parameters ──

@router.post("/experiments/{experiment_id}/parameters", status_code=201)
async def log_parameter(
    experiment_id: int,
    key: str = Query(...), value: str = Query(...),
    param_type: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    ep = await svc.log_parameter(experiment_id, key, value, param_type=param_type)
    return {"id": ep.id, "key": ep.key, "value": ep.value}


@router.post("/experiments/{experiment_id}/parameters/batch", status_code=201)
async def log_parameters_batch(
    experiment_id: int,
    params: str = Query(...),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    parsed = _parse_json(params)
    items = await svc.log_parameters(experiment_id, parsed)
    return {"count": len(items)}


@router.get("/experiments/{experiment_id}/parameters")
async def get_parameters(
    experiment_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.get_parameters(experiment_id)
    return {"parameters": {p.key: {"value": p.value, "type": p.param_type} for p in items}}


# ── Metrics ──

@router.post("/experiments/{experiment_id}/metrics", status_code=201)
async def log_metric(
    experiment_id: int,
    key: str = Query(...), value: float = Query(...),
    step: int | None = None, epoch: int | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    em = await svc.log_metric(experiment_id, key, value, step=step, epoch=epoch)
    return {"id": em.id, "key": em.key, "value": em.value, "step": em.step}


@router.post("/experiments/{experiment_id}/metrics/batch", status_code=201)
async def log_metrics_batch(
    experiment_id: int,
    metrics: str = Query(...),
    step: int | None = None, epoch: int | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    parsed = _parse_json(metrics)
    items = await svc.log_metrics(experiment_id, parsed, step=step, epoch=epoch)
    return {"count": len(items)}


@router.get("/experiments/{experiment_id}/metrics")
async def get_metrics(
    experiment_id: int,
    key: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.get_metrics(experiment_id, key=key)
    return {"metrics": [_met_dict(m) for m in items]}


@router.get("/experiments/{experiment_id}/metrics/{key}/history")
async def get_metric_history(
    experiment_id: int, key: str,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.get_metric_history(experiment_id, key)
    return {"key": key, "values": [{"value": m.value, "step": m.step, "epoch": m.epoch, "created_at": m.created_at.isoformat() if m.created_at else None} for m in items]}


@router.post("/experiments/{experiment_id}/best-metric-direction")
async def set_best_metric_direction(
    experiment_id: int,
    key: str = Query(...), direction: str = Query(...),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    exp = await svc.set_best_metric_direction(experiment_id, key, direction)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return {"best_metric_name": exp.best_metric_name, "best_metric_value": exp.best_metric_value, "direction": exp.best_metric_direction}


# ── Artifacts ──

@router.post("/experiments/{experiment_id}/artifacts", status_code=201)
async def log_artifact(
    experiment_id: int,
    name: str = Query(...),
    description: str | None = None,
    artifact_type: str = "file",
    file_path: str | None = None,
    file_size_bytes: int | None = None,
    uri: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    art = await svc.log_artifact(
        experiment_id=experiment_id, name=name,
        description=description, artifact_type=artifact_type,
        file_path=file_path, file_size_bytes=file_size_bytes,
        uri=uri, metadata=_parse_json(metadata),
    )
    return {"id": art.id, "name": art.name, "artifact_type": art.artifact_type}


@router.get("/experiments/{experiment_id}/artifacts")
async def get_artifacts(
    experiment_id: int,
    artifact_type: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.get_artifacts(experiment_id, artifact_type=artifact_type)
    return {"artifacts": [_art_dict(a) for a in items]}


# ── Charts ──

@router.post("/experiments/{experiment_id}/charts", status_code=201)
async def log_chart(
    experiment_id: int,
    name: str = Query(...),
    chart_type: str = "line",
    chart_config: str | None = None,
    data: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    ch = await svc.log_chart(
        experiment_id=experiment_id, name=name,
        chart_type=chart_type, chart_config=_parse_json(chart_config),
        data=_parse_json(data), metadata=_parse_json(metadata),
    )
    return {"id": ch.id, "name": ch.name, "chart_type": ch.chart_type}


@router.get("/experiments/{experiment_id}/charts")
async def get_charts(
    experiment_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.get_charts(experiment_id)
    return {"charts": [_chart_dict(c) for c in items]}


# ── Tags ──

@router.post("/experiments/{experiment_id}/tags", status_code=201)
async def add_tag(
    experiment_id: int,
    key: str = Query(...), value: str = Query(...),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    tag = await svc.add_tag(experiment_id, key, value)
    return {"id": tag.id, "key": tag.key, "value": tag.value}


@router.get("/experiments/{experiment_id}/tags")
async def get_tags(
    experiment_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.get_tags(experiment_id)
    return {"tags": {t.key: t.value for t in items}}


@router.get("/experiments/by-tag")
async def find_by_tag(
    key: str = Query(...), value: str = Query(...),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    items = await svc.find_by_tag(key, value)
    return PaginatedResponse(items=[_exp_dict(e) for e in items], total=len(items), limit=len(items), offset=0)


# ── Best Model ──

@router.get("/best-model")
async def find_best_experiment(
    metric_name: str = Query(...),
    direction: str = "max",
    status: str | None = "completed",
    tags: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    exp = await svc.find_best_experiment(
        metric_name=metric_name, direction=direction,
        status=status, tags=_parse_json(tags),
    )
    if not exp:
        raise HTTPException(404, "No best experiment found")
    return _exp_dict(exp)


# ── Summary ──

@router.get("/experiments/{experiment_id}/summary")
async def get_experiment_summary(
    experiment_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = ExperimentManagerService(session)
    summary = await svc.get_experiment_summary(experiment_id)
    if not summary:
        raise HTTPException(404, "Experiment not found")
    return summary


# ── Helpers ──

def _parse_json(val: str | None) -> Any:
    if val is None:
        return None
    import json as _json
    return _json.loads(val)


def _exp_dict(exp: Any) -> dict:
    return {
        "id": exp.id, "experiment_id": exp.experiment_id,
        "name": exp.name, "description": exp.description,
        "status": exp.status,
        "best_metric_name": exp.best_metric_name,
        "best_metric_value": exp.best_metric_value,
        "duration_seconds": exp.duration_seconds,
        "started_at": exp.started_at.isoformat() if exp.started_at else None,
        "completed_at": exp.completed_at.isoformat() if exp.completed_at else None,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
    }


def _met_dict(m: Any) -> dict:
    return {
        "id": m.id, "key": m.key, "value": m.value,
        "step": m.step, "epoch": m.epoch,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _art_dict(a: Any) -> dict:
    return {
        "id": a.id, "name": a.name, "description": a.description,
        "artifact_type": a.artifact_type, "file_path": a.file_path,
        "file_size_bytes": a.file_size_bytes, "uri": a.uri,
    }


def _chart_dict(c: Any) -> dict:
    return {
        "id": c.id, "name": c.name, "chart_type": c.chart_type,
    }
