from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api import deps
from titan_x.models.user import User
from titan_x.api.schemas import PaginatedResponse
from titan_x.services.automated_training_service import AutomatedTrainingService

router = APIRouter(tags=["automated-training"])


# ── Dataset Versioning ──

@router.post("/datasets", status_code=201)
async def create_dataset(
    name: str = Query(...),
    version: str = Query(...),
    description: str | None = None,
    source: str | None = None,
    row_count: int | None = None,
    size_bytes: int | None = None,
    checksum: str | None = None,
    metadata: str | None = None,  # JSON string
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    ds = await svc.create_dataset(
        name=name, version=version, description=description,
        source=source, row_count=row_count, size_bytes=size_bytes,
        checksum=checksum,
        metadata=__import__("json").loads(metadata) if metadata else None,
    )
    return {"id": ds.id, "name": ds.name, "version": ds.version}


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    ds = await svc.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return _dataset_dict(ds)


@router.get("/datasets")
async def list_datasets(
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.list_datasets(limit=limit, offset=offset)
    total = await svc.count_datasets()
    return PaginatedResponse(items=[_dataset_dict(d) for d in items], total=total, limit=limit, skip=offset)


# ── Feature Sets ──

@router.post("/feature-sets", status_code=201)
async def create_feature_set(
    name: str = Query(...),
    description: str | None = None,
    features: str | None = None,  # JSON list
    target_column: str | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    fs = await svc.create_feature_set(
        name=name, description=description,
        features=__import__("json").loads(features) if features else None,
        target_column=target_column,
        metadata=__import__("json").loads(metadata) if metadata else None,
    )
    return {"id": fs.id, "name": fs.name, "feature_count": fs.feature_count}


@router.get("/feature-sets/{fs_id}")
async def get_feature_set(
    fs_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    fs = await svc.get_feature_set(fs_id)
    if not fs:
        raise HTTPException(404, "Feature set not found")
    return _feat_dict(fs)


@router.get("/feature-sets")
async def list_feature_sets(
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.list_feature_sets(limit=limit, offset=offset)
    return PaginatedResponse(items=[_feat_dict(f) for f in items], total=await svc.count_feature_sets(), limit=limit, skip=offset)


# ── Hyperparameter Configs ──

@router.post("/hyperparameter-configs", status_code=201)
async def create_hyperparameter_config(
    name: str = Query(...),
    description: str | None = None,
    parameters: str | None = None,  # JSON object
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    hp = await svc.create_hyperparameter_config(
        name=name, description=description,
        parameters=__import__("json").loads(parameters) if parameters else None,
        metadata=__import__("json").loads(metadata) if metadata else None,
    )
    return {"id": hp.id, "name": hp.name}


@router.get("/hyperparameter-configs/{hp_id}")
async def get_hyperparameter_config(
    hp_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    hp = await svc.get_hyperparameter_config(hp_id)
    if not hp:
        raise HTTPException(404, "Hyperparameter config not found")
    return _hp_dict(hp)


@router.get("/hyperparameter-configs")
async def list_hyperparameter_configs(
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.list_hyperparameter_configs(limit=limit, offset=offset)
    return PaginatedResponse(items=[_hp_dict(h) for h in items], total=await svc.count_hyperparameter_configs(), limit=limit, skip=offset)


# ── Training Jobs ──

@router.post("/jobs", status_code=201)
async def create_job(
    name: str = Query(...),
    description: str | None = None,
    model_registry_entry_id: int | None = None,
    dataset_version_id: int | None = None,
    feature_set_id: int | None = None,
    hyperparameter_config_id: int | None = None,
    schedule: str | None = None,
    priority: int = 0,
    gpu_required: bool = False,
    gpu_memory_required_mb: int | None = None,
    max_epochs: int = 10,
    max_steps: int | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.create_job(
        name=name, description=description,
        model_registry_entry_id=model_registry_entry_id,
        dataset_version_id=dataset_version_id,
        feature_set_id=feature_set_id,
        hyperparameter_config_id=hyperparameter_config_id,
        schedule=schedule, priority=priority,
        gpu_required=gpu_required, gpu_memory_required_mb=gpu_memory_required_mb,
        max_epochs=max_epochs, max_steps=max_steps,
    )
    return _job_dict(job)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_dict(job)


@router.get("/jobs")
async def list_jobs(
    status: str | None = None,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.list_jobs(status=status, limit=limit, offset=offset)
    return PaginatedResponse(items=[_job_dict(j) for j in items], total=await svc.count_jobs(status), limit=limit, skip=offset)


@router.post("/jobs/{job_id}/start")
async def start_job(
    job_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.update_job_status(job_id, "running")
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_dict(job)


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.update_job_status(job_id, "paused")
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_dict(job)


@router.post("/jobs/{job_id}/complete")
async def complete_job(
    job_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.update_job_status(job_id, "completed")
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_dict(job)


@router.post("/jobs/{job_id}/fail")
async def fail_job(
    job_id: int,
    error_message: str = Query(...),
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.update_job_status(job_id, "failed", error_message=error_message)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_dict(job)


@router.post("/jobs/{job_id}/progress")
async def update_progress(
    job_id: int,
    current_epoch: int | None = None,
    current_step: int | None = None,
    loss_value: float | None = None,
    best_loss: float | None = None,
    metric_value: float | None = None,
    best_metric: float | None = None,
    training_duration_seconds: float | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.update_job_progress(
        job_id, current_epoch=current_epoch, current_step=current_step,
        loss_value=loss_value, best_loss=best_loss,
        metric_value=metric_value, best_metric=best_metric,
        training_duration_seconds=training_duration_seconds,
    )
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_dict(job)


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    job = await svc.resume_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found or not resumable")
    return _job_dict(job)


# ── Checkpoints ──

@router.post("/jobs/{job_id}/checkpoints", status_code=201)
async def create_checkpoint(
    job_id: int,
    epoch: int = Query(...),
    step: int | None = None,
    metric_value: float | None = None,
    loss_value: float | None = None,
    artifact_path: str | None = None,
    file_size_bytes: int | None = None,
    metadata: str | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    cp = await svc.create_checkpoint(
        job_id=job_id, epoch=epoch, step=step,
        metric_value=metric_value, loss_value=loss_value,
        artifact_path=artifact_path, file_size_bytes=file_size_bytes,
        metadata=__import__("json").loads(metadata) if metadata else None,
    )
    return {"id": cp.id, "epoch": cp.epoch, "metric_value": cp.metric_value}


@router.get("/jobs/{job_id}/checkpoints")
async def list_checkpoints(
    job_id: int,
    limit: int = 50, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.list_checkpoints(job_id, limit=limit, offset=offset)
    return PaginatedResponse(items=[_cp_dict(c) for c in items], total=await svc.count_checkpoints(job_id), limit=limit, skip=offset)


@router.get("/jobs/{job_id}/checkpoints/latest")
async def get_latest_checkpoint(
    job_id: int,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    cp = await svc.get_latest_checkpoint(job_id)
    if not cp:
        raise HTTPException(404, "No checkpoint found")
    return _cp_dict(cp)


# ── Logs ──

@router.post("/jobs/{job_id}/logs", status_code=201)
async def add_log(
    job_id: int,
    level: str = Query(default="info"),
    message: str = Query(...),
    epoch: int | None = None,
    step: int | None = None,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    log = await svc.add_log(job_id, level=level, message=message, epoch=epoch, step=step)
    return {"id": log.id, "level": log.level, "message": log.message}


@router.get("/jobs/{job_id}/logs")
async def get_logs(
    job_id: int,
    level: str | None = None,
    limit: int = 100, offset: int = 0,
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.get_logs(job_id, level=level, limit=limit, offset=offset)
    return PaginatedResponse(items=[_log_dict(l) for l in items], total=await svc.count_logs(job_id, level), limit=limit, skip=offset)


# ── Scheduling ──

@router.get("/scheduled/due")
async def get_due_jobs(
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.get_due_scheduled_jobs()
    return PaginatedResponse(items=[_job_dict(j) for j in items], total=len(items), limit=len(items), skip=0)


@router.get("/scheduled/pending")
async def get_pending_jobs(
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.get_pending_jobs()
    return PaginatedResponse(items=[_job_dict(j) for j in items], total=len(items), limit=len(items), skip=0)


@router.get("/scheduled/running")
async def get_running_jobs(
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.get_running_jobs()
    return PaginatedResponse(items=[_job_dict(j) for j in items], total=len(items), limit=len(items), skip=0)


@router.get("/gpu-jobs")
async def get_gpu_jobs(
    session=Depends(deps.get_session),
    _: User = Depends(deps.get_current_active_superuser),
):
    svc = AutomatedTrainingService(session)
    items = await svc.get_gpu_jobs()
    return PaginatedResponse(items=[_job_dict(j) for j in items], total=len(items), limit=len(items), skip=0)


# ── Helpers ──

def _dataset_dict(ds: Any) -> dict:
    return {
        "id": ds.id, "name": ds.name, "version": ds.version,
        "description": ds.description, "source": ds.source,
        "row_count": ds.row_count, "size_bytes": ds.size_bytes,
        "checksum": ds.checksum, "status": ds.status,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


def _feat_dict(fs: Any) -> dict:
    return {
        "id": fs.id, "name": fs.name, "description": fs.description,
        "target_column": fs.target_column, "feature_count": fs.feature_count,
        "status": fs.status, "created_at": fs.created_at.isoformat() if fs.created_at else None,
    }


def _hp_dict(hp: Any) -> dict:
    return {
        "id": hp.id, "name": hp.name, "description": hp.description,
        "status": hp.status, "created_at": hp.created_at.isoformat() if hp.created_at else None,
    }


def _job_dict(job: Any) -> dict:
    return {
        "id": job.id, "name": job.name, "description": job.description,
        "model_registry_entry_id": job.model_registry_entry_id,
        "dataset_version_id": job.dataset_version_id,
        "feature_set_id": job.feature_set_id,
        "hyperparameter_config_id": job.hyperparameter_config_id,
        "status": job.status, "schedule": job.schedule,
        "priority": job.priority,
        "gpu_required": job.gpu_required,
        "gpu_memory_required_mb": job.gpu_memory_required_mb,
        "max_epochs": job.max_epochs, "current_epoch": job.current_epoch,
        "max_steps": job.max_steps, "current_step": job.current_step,
        "loss_value": job.loss_value, "best_loss": job.best_loss,
        "metric_value": job.metric_value, "best_metric": job.best_metric,
        "training_duration_seconds": job.training_duration_seconds,
        "artifact_path": job.artifact_path, "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def _cp_dict(cp: Any) -> dict:
    return {
        "id": cp.id, "job_id": cp.job_id, "epoch": cp.epoch,
        "step": cp.step, "metric_value": cp.metric_value,
        "loss_value": cp.loss_value, "artifact_path": cp.artifact_path,
        "file_size_bytes": cp.file_size_bytes,
        "created_at": cp.created_at.isoformat() if cp.created_at else None,
    }


def _log_dict(log: Any) -> dict:
    return {
        "id": log.id, "job_id": log.job_id, "level": log.level,
        "message": log.message, "epoch": log.epoch, "step": log.step,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
