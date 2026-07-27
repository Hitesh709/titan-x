import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.automated_training import (
    DatasetVersion,
    FeatureSet,
    HyperparameterConfig,
    TrainingJob,
    TrainingJobCheckpoint,
    TrainingJobLog,
)


class AutomatedTrainingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Dataset Versioning ──

    async def create_dataset(
        self, name: str, version: str,
        description: str | None = None,
        source: str | None = None,
        schema_json: str | None = None,
        row_count: int | None = None,
        size_bytes: int | None = None,
        checksum: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DatasetVersion:
        ds = DatasetVersion(
            name=name, version=version,
            description=description, source=source,
            schema_json=schema_json,
            row_count=row_count, size_bytes=size_bytes,
            checksum=checksum,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(ds)
        await self.session.flush()
        await self.session.refresh(ds)
        return ds

    async def get_dataset(self, dataset_id: int) -> DatasetVersion | None:
        return await self.session.get(DatasetVersion, dataset_id)

    async def list_datasets(self, limit: int = 50, offset: int = 0) -> list[DatasetVersion]:
        r = await self.session.execute(
            select(DatasetVersion)
            .order_by(desc(DatasetVersion.created_at))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ── Feature Sets ──

    async def create_feature_set(
        self, name: str,
        description: str | None = None,
        features: list[str] | None = None,
        target_column: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureSet:
        fs = FeatureSet(
            name=name, description=description,
            features_json=json.dumps(features) if features else None,
            target_column=target_column,
            feature_count=len(features) if features else None,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(fs)
        await self.session.flush()
        await self.session.refresh(fs)
        return fs

    async def get_feature_set(self, fs_id: int) -> FeatureSet | None:
        return await self.session.get(FeatureSet, fs_id)

    async def list_feature_sets(self, limit: int = 50, offset: int = 0) -> list[FeatureSet]:
        r = await self.session.execute(
            select(FeatureSet)
            .order_by(desc(FeatureSet.created_at))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ── Hyperparameter Configs ──

    async def create_hyperparameter_config(
        self, name: str,
        parameters: dict[str, Any] | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HyperparameterConfig:
        hp = HyperparameterConfig(
            name=name, description=description,
            parameters_json=json.dumps(parameters) if parameters else None,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(hp)
        await self.session.flush()
        await self.session.refresh(hp)
        return hp

    async def get_hyperparameter_config(self, hp_id: int) -> HyperparameterConfig | None:
        return await self.session.get(HyperparameterConfig, hp_id)

    async def list_hyperparameter_configs(self, limit: int = 50, offset: int = 0) -> list[HyperparameterConfig]:
        r = await self.session.execute(
            select(HyperparameterConfig)
            .order_by(desc(HyperparameterConfig.created_at))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ── Training Jobs ──

    async def create_job(
        self, name: str,
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
    ) -> TrainingJob:
        job = TrainingJob(
            name=name, description=description,
            model_registry_entry_id=model_registry_entry_id,
            dataset_version_id=dataset_version_id,
            feature_set_id=feature_set_id,
            hyperparameter_config_id=hyperparameter_config_id,
            schedule=schedule, priority=priority,
            gpu_required=gpu_required,
            gpu_memory_required_mb=gpu_memory_required_mb,
            max_epochs=max_epochs, max_steps=max_steps,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_job(self, job_id: int) -> TrainingJob | None:
        return await self.session.get(TrainingJob, job_id)

    async def list_jobs(
        self, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[TrainingJob]:
        q = select(TrainingJob)
        if status:
            q = q.where(TrainingJob.status == status)
        q = q.order_by(desc(TrainingJob.priority), desc(TrainingJob.created_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def update_job_status(
        self, job_id: int, status: str,
        error_message: str | None = None,
    ) -> TrainingJob | None:
        job = await self.get_job(job_id)
        if not job:
            return None
        job.status = status
        if error_message:
            job.error_message = error_message
        if status == "running" and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        if status in ("completed", "failed"):
            job.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def update_job_progress(
        self, job_id: int,
        current_epoch: int | None = None,
        current_step: int | None = None,
        loss_value: float | None = None,
        best_loss: float | None = None,
        metric_value: float | None = None,
        best_metric: float | None = None,
        training_duration_seconds: float | None = None,
    ) -> TrainingJob | None:
        job = await self.get_job(job_id)
        if not job:
            return None
        if current_epoch is not None:
            job.current_epoch = current_epoch
        if current_step is not None:
            job.current_step = current_step
        if loss_value is not None:
            job.loss_value = loss_value
        if best_loss is not None:
            job.best_loss = best_loss
        if metric_value is not None:
            job.metric_value = metric_value
        if best_metric is not None:
            job.best_metric = best_metric
        if training_duration_seconds is not None:
            job.training_duration_seconds = training_duration_seconds
        await self.session.flush()
        await self.session.refresh(job)
        return job

    # ── Checkpointing ──

    async def create_checkpoint(
        self, job_id: int, epoch: int,
        step: int | None = None,
        metric_value: float | None = None,
        loss_value: float | None = None,
        artifact_path: str | None = None,
        file_size_bytes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TrainingJobCheckpoint:
        cp = TrainingJobCheckpoint(
            job_id=job_id, epoch=epoch, step=step,
            metric_value=metric_value, loss_value=loss_value,
            artifact_path=artifact_path, file_size_bytes=file_size_bytes,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(cp)
        await self.session.flush()
        await self.session.refresh(cp)
        return cp

    async def get_latest_checkpoint(self, job_id: int) -> TrainingJobCheckpoint | None:
        r = await self.session.execute(
            select(TrainingJobCheckpoint)
            .where(TrainingJobCheckpoint.job_id == job_id)
            .order_by(desc(TrainingJobCheckpoint.epoch), desc(TrainingJobCheckpoint.step))
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def list_checkpoints(
        self, job_id: int, limit: int = 50, offset: int = 0,
    ) -> list[TrainingJobCheckpoint]:
        r = await self.session.execute(
            select(TrainingJobCheckpoint)
            .where(TrainingJobCheckpoint.job_id == job_id)
            .order_by(desc(TrainingJobCheckpoint.epoch))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    async def resume_job(self, job_id: int) -> TrainingJob | None:
        job = await self.get_job(job_id)
        if not job:
            return None
        if job.status not in ("failed", "paused"):
            return None
        cp = await self.get_latest_checkpoint(job_id)
        job.status = "running"
        if not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    # ── Logging ──

    async def add_log(
        self, job_id: int, level: str, message: str,
        epoch: int | None = None,
        step: int | None = None,
    ) -> TrainingJobLog:
        log = TrainingJobLog(
            job_id=job_id, level=level, message=message,
            epoch=epoch, step=step,
        )
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log

    async def get_logs(
        self, job_id: int,
        level: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[TrainingJobLog]:
        q = select(TrainingJobLog).where(TrainingJobLog.job_id == job_id)
        if level:
            q = q.where(TrainingJobLog.level == level)
        q = q.order_by(desc(TrainingJobLog.created_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    # ── Scheduled Jobs ──

    async def get_due_scheduled_jobs(self) -> list[TrainingJob]:
        r = await self.session.execute(
            select(TrainingJob).where(
                TrainingJob.schedule.isnot(None),
                TrainingJob.status.in_(["pending", "completed", "failed"]),
            ).order_by(TrainingJob.priority)
        )
        return list(r.scalars().all())

    async def get_pending_jobs(self) -> list[TrainingJob]:
        r = await self.session.execute(
            select(TrainingJob)
            .where(TrainingJob.status == "pending")
            .order_by(desc(TrainingJob.priority), TrainingJob.created_at)
        )
        return list(r.scalars().all())

    async def get_running_jobs(self) -> list[TrainingJob]:
        r = await self.session.execute(
            select(TrainingJob)
            .where(TrainingJob.status == "running")
            .order_by(TrainingJob.started_at)
        )
        return list(r.scalars().all())

    async def get_gpu_jobs(self) -> list[TrainingJob]:
        r = await self.session.execute(
            select(TrainingJob)
            .where(TrainingJob.gpu_required == True)
            .order_by(desc(TrainingJob.priority))
        )
        return list(r.scalars().all())

