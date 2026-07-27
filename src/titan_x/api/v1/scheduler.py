from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_scheduler_service, require_api_key
from titan_x.api.schemas import MessageResponse
from titan_x.models.job import Job
from titan_x.services.scheduler_service import SchedulerService

scheduler_router = APIRouter(prefix="/scheduler", tags=["scheduler"], dependencies=[Depends(require_api_key)])


class JobResponse(BaseModel):
    id: int
    name: str
    description: str | None
    job_type: str
    schedule_type: str
    cron_expr: str | None
    schedule_time: str | None
    timezone: str
    enabled: bool
    max_retries: int
    retry_delay_seconds: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    run_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime


class JobCreateRequest(BaseModel):
    name: str
    description: str | None = None
    job_type: str
    schedule_type: str = "daily"
    cron_expr: str | None = None
    schedule_time: str | None = None
    timezone: str = "UTC"
    enabled: bool = True
    max_retries: int = 3
    retry_delay_seconds: int = 60


class JobUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    cron_expr: str | None = None
    schedule_time: str | None = None
    timezone: str | None = None
    enabled: bool | None = None
    max_retries: int | None = None
    retry_delay_seconds: int | None = None


class JobExecutionResponse(BaseModel):
    id: int
    job_id: int
    job_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None
    retry_attempt: int


class JobStatsResponse(BaseModel):
    total_jobs: int
    enabled_jobs: int
    running_jobs: int
    failed_jobs: int


@scheduler_router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreateRequest,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> JobResponse:
    try:
        job = await service.create_job(
            name=body.name,
            description=body.description,
            job_type=body.job_type,
            schedule_type=body.schedule_type,
            cron_expr=body.cron_expr,
            schedule_time=body.schedule_time,
            timezone=body.timezone,
            enabled=body.enabled,
            max_retries=body.max_retries,
            retry_delay_seconds=body.retry_delay_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return JobResponse(**job.__dict__)


@scheduler_router.get("", response_model=list[JobResponse])
async def list_jobs(
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> list[JobResponse]:
    jobs = await service.list_jobs(skip=skip, limit=limit)
    return [JobResponse(**j.__dict__) for j in jobs]


@scheduler_router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> JobResponse:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse(**job.__dict__)


@scheduler_router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    body: JobUpdateRequest,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> JobResponse:
    updates = body.model_dump(exclude_unset=True)
    job = await service.update_job(job_id, **updates)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse(**job.__dict__)


@scheduler_router.delete("/{job_id}", response_model=MessageResponse)
async def delete_job(
    job_id: int,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> MessageResponse:
    deleted = await service.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return MessageResponse(message="Job deleted")


@scheduler_router.post("/{job_id}/enable", response_model=JobResponse)
async def enable_job(
    job_id: int,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> JobResponse:
    job = await service.enable_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse(**job.__dict__)


@scheduler_router.post("/{job_id}/disable", response_model=JobResponse)
async def disable_job(
    job_id: int,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> JobResponse:
    job = await service.disable_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse(**job.__dict__)


@scheduler_router.post("/{job_id}/run", response_model=JobResponse)
async def run_job_now(
    job_id: int,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> JobResponse:
    try:
        await service.run_job_now(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    job = await service.get_job(job_id)
    return JobResponse(**job.__dict__)


@scheduler_router.get("/{job_id}/executions", response_model=list[JobExecutionResponse])
async def get_job_executions(
    job_id: int,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> list[JobExecutionResponse]:
    executions = await service.get_executions(job_id, skip=skip, limit=limit)
    return [JobExecutionResponse(**e.__dict__) for e in executions]
