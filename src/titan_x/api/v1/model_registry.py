import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.services.model_registry_service import ModelRegistryService

router = APIRouter(prefix="/model-registry", tags=["model_registry"])


def _loads_json(value: str | None) -> Any | None:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON in request")


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> ModelRegistryService:
    return ModelRegistryService(session)


def _entry_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "name": e.name,
        "description": e.description,
        "model_type": e.model_type,
        "framework": e.framework,
        "status": e.status,
        "tags": e.tags_json,
        "metadata": e.metadata_json,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _version_dict(v: Any) -> dict[str, Any]:
    return {
        "id": v.id,
        "entry_id": v.entry_id,
        "version": v.version,
        "description": v.description,
        "status": v.status,
        "source": v.source,
        "is_active": v.is_active,
        "changelog": v.changelog,
        "metadata": v.metadata_json,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _training_run_dict(tr: Any) -> dict[str, Any]:
    return {
        "id": tr.id,
        "version_id": tr.version_id,
        "run_id": tr.run_id,
        "dataset_info": tr.dataset_info_json,
        "hyperparameters": tr.hyperparameters_json,
        "training_duration_seconds": tr.training_duration_seconds,
        "status": tr.status,
        "metrics": tr.metrics_json,
        "artifact_path": tr.artifact_path,
        "started_at": tr.started_at.isoformat() if tr.started_at else None,
        "completed_at": tr.completed_at.isoformat() if tr.completed_at else None,
        "notes": tr.notes,
        "created_at": tr.created_at.isoformat() if tr.created_at else None,
    }


# ── Entry Endpoints ──


@router.post("/entries", summary="Register a new AI model entry")
async def register_entry(
    name: str = Query(...),
    model_type: str = Query(...),
    description: str | None = Query(None),
    framework: str | None = Query(None),
    tags: str | None = Query(None),
    metadata: str | None = Query(None),
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    entry = await service.register_entry(
        name=name, model_type=model_type,
        description=description, framework=framework,
        tags=_loads_json(tags),
        metadata=_loads_json(metadata),
    )
    return {"entry": _entry_dict(entry)}


@router.get("/entries", summary="List model entries")
async def list_entries(
    model_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    service: ModelRegistryService = Depends(_get_service),
):
    entries = await service.list_entries(
        model_type=model_type, status=status,
        limit=limit, offset=offset,
    )
    return {"total": await service.count_entries(model_type=model_type, status=status), "entries": [_entry_dict(e) for e in entries]}


@router.get("/entries/{entry_id}", summary="Get a model entry")
async def get_entry(
    entry_id: int,
    service: ModelRegistryService = Depends(_get_service),
):
    entry = await service.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"entry": _entry_dict(entry)}


@router.put("/entries/{entry_id}", summary="Update a model entry")
async def update_entry(
    entry_id: int,
    description: str | None = Query(None),
    framework: str | None = Query(None),
    status: str | None = Query(None),
    tags: str | None = Query(None),
    metadata: str | None = Query(None),
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    entry = await service.update_entry(
        entry_id=entry_id,
        description=description, framework=framework,
        status=status,
        tags=_loads_json(tags),
        metadata=_loads_json(metadata),
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"entry": _entry_dict(entry)}


# ── Version Endpoints ──


@router.post("/entries/{entry_id}/versions", summary="Create a new version for an entry")
async def create_version(
    entry_id: int,
    version: str = Query(...),
    description: str | None = Query(None),
    source: str | None = Query(None),
    changelog: str | None = Query(None),
    metadata: str | None = Query(None),
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    v = await service.create_version(
        entry_id=entry_id, version=version,
        description=description, source=source,
        changelog=changelog,
        metadata=_loads_json(metadata),
    )
    return {"version": _version_dict(v)}


@router.get("/entries/{entry_id}/versions", summary="List versions for an entry")
async def list_versions(
    entry_id: int,
    limit: int = Query(50),
    offset: int = Query(0),
    service: ModelRegistryService = Depends(_get_service),
):
    versions = await service.get_versions(
        entry_id=entry_id, limit=limit, offset=offset,
    )
    return {"total": await service.count_versions(entry_id=entry_id), "versions": [_version_dict(v) for v in versions]}


@router.put("/versions/{version_id}", summary="Update a version")
async def update_version(
    version_id: int,
    description: str | None = Query(None),
    source: str | None = Query(None),
    changelog: str | None = Query(None),
    status: str | None = Query(None),
    metadata: str | None = Query(None),
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    v = await service.update_version(
        version_id=version_id,
        description=description, source=source,
        changelog=changelog, status=status,
        metadata=_loads_json(metadata),
    )
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"version": _version_dict(v)}


@router.post("/versions/{version_id}/activate", summary="Set as active version")
async def activate_version(
    version_id: int,
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    v = await service.set_active_version(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"version": _version_dict(v)}


@router.get("/entries/{entry_id}/active", summary="Get active version for an entry")
async def get_active_version(
    entry_id: int,
    service: ModelRegistryService = Depends(_get_service),
):
    v = await service.get_active_version(entry_id)
    if not v:
        raise HTTPException(status_code=404, detail="No active version found")
    return {"version": _version_dict(v)}


# ── Training Run Endpoints ──


@router.post("/versions/{version_id}/training-runs", summary="Record a training run")
async def create_training_run(
    version_id: int,
    run_id: str | None = Query(None),
    dataset_info: str | None = Query(None),
    hyperparameters: str | None = Query(None),
    training_duration_seconds: float | None = Query(None),
    status: str = Query("completed"),
    metrics: str | None = Query(None),
    artifact_path: str | None = Query(None),
    started_at: datetime | None = Query(None),
    completed_at: datetime | None = Query(None),
    notes: str | None = Query(None),
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    tr = await service.create_training_run(
        version_id=version_id,
        run_id=run_id,
        dataset_info=_loads_json(dataset_info),
        hyperparameters=_loads_json(hyperparameters),
        training_duration_seconds=training_duration_seconds,
        status=status,
        metrics=_loads_json(metrics),
        artifact_path=artifact_path,
        started_at=started_at,
        completed_at=completed_at,
        notes=notes,
    )
    return {"training_run": _training_run_dict(tr)}


@router.get("/versions/{version_id}/training-runs", summary="List training runs for a version")
async def list_training_runs(
    version_id: int,
    limit: int = Query(50),
    offset: int = Query(0),
    service: ModelRegistryService = Depends(_get_service),
):
    runs = await service.list_training_runs(
        version_id=version_id, limit=limit, offset=offset,
    )
    return {"total": await service.count_training_runs(version_id=version_id), "training_runs": [_training_run_dict(r) for r in runs]}


# ── Metrics Endpoints ──


@router.post("/versions/{version_id}/metrics", summary="Record a metric for a version")
async def record_metric(
    version_id: int,
    metric_name: str = Query(...),
    metric_value: float = Query(...),
    metric_type: str = Query("float"),
    dataset_type: str = Query("validation"),
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    metric = await service.record_metric(
        version_id=version_id,
        metric_name=metric_name,
        metric_value=metric_value,
        metric_type=metric_type,
        dataset_type=dataset_type,
    )
    return {"metric": {"id": metric.id, "name": metric.metric_name, "value": metric.metric_value}}


@router.get("/versions/{version_id}/metrics", summary="Get metrics for a version")
async def get_metrics(
    version_id: int,
    metric_name: str | None = Query(None),
    dataset_type: str | None = Query(None),
    service: ModelRegistryService = Depends(_get_service),
):
    metrics = await service.get_metrics(
        version_id=version_id,
        metric_name=metric_name,
        dataset_type=dataset_type,
    )
    return {"metrics": [{"id": m.id, "name": m.metric_name, "value": m.metric_value, "dataset": m.dataset_type} for m in metrics]}


# ── Deployment & Rollback Endpoints ──


@router.post("/versions/{version_id}/deploy", summary="Deploy a version to an environment")
async def deploy(
    version_id: int,
    environment: str = Query(...),
    notes: str | None = Query(None),
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    try:
        dep = await service.deploy(
            version_id=version_id,
            environment=environment,
            deployed_by=current_user.email,
            notes=notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"deployment": {"id": dep.id, "version_id": dep.version_id, "environment": dep.environment, "status": dep.status}}


@router.post("/environments/{environment}/rollback", summary="Rollback deployment in an environment")
async def rollback(
    environment: str,
    service: ModelRegistryService = Depends(_get_service),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    dep = await service.rollback(
        environment=environment,
        rolled_by=current_user.email,
    )
    if not dep:
        raise HTTPException(status_code=400, detail="No rollback target available")
    return {"deployment": {"id": dep.id, "version_id": dep.version_id, "environment": dep.environment, "status": dep.status}}


@router.get("/environments/{environment}/active", summary="Get active deployment in an environment")
async def get_active_deployment(
    environment: str,
    service: ModelRegistryService = Depends(_get_service),
):
    dep = await service.get_active_deployment(environment)
    if not dep:
        raise HTTPException(status_code=404, detail="No active deployment in this environment")
    return {"deployment": {"id": dep.id, "version_id": dep.version_id, "environment": dep.environment, "status": dep.status}}


@router.get("/environments/{environment}/history", summary="Get deployment history for an environment")
async def get_deployment_history(
    environment: str,
    service: ModelRegistryService = Depends(_get_service),
):
    history = await service.get_deployment_history(environment)
    return {"history": [{"id": d.id, "version_id": d.version_id, "status": d.status, "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None} for d in history]}


# ── Compare Endpoint ──


@router.post("/compare", summary="Compare multiple versions")
async def compare_versions(
    version_ids: list[int] = Query(...),
    service: ModelRegistryService = Depends(_get_service),
):
    results = await service.compare_versions(version_ids)
    return {"comparison": results}


import json
