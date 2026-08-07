import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.model_registry import (
    ModelMetric,
    ModelRegistryDeployment,
    ModelRegistryEntry,
    ModelRegistryVersion,
    ModelTrainingRun,
)


class ModelRegistryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Entry CRUD ──

    async def register_entry(
        self, name: str, model_type: str,
        description: str | None = None,
        framework: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelRegistryEntry:
        entry = ModelRegistryEntry(
            name=name,
            model_type=model_type,
            description=description,
            framework=framework,
            tags_json=json.dumps(tags) if tags else None,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_entry(self, entry_id: int) -> ModelRegistryEntry | None:
        return await self.session.get(ModelRegistryEntry, entry_id)

    async def get_entry_by_name(self, name: str) -> ModelRegistryEntry | None:
        r = await self.session.execute(
            select(ModelRegistryEntry).where(ModelRegistryEntry.name == name)
        )
        return r.scalar_one_or_none()

    async def list_entries(
        self, model_type: str | None = None,
        status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[ModelRegistryEntry]:
        q = select(ModelRegistryEntry)
        if model_type:
            q = q.where(ModelRegistryEntry.model_type == model_type)
        if status:
            q = q.where(ModelRegistryEntry.status == status)
        q = q.order_by(desc(ModelRegistryEntry.created_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def count_entries(self, model_type: str | None = None, status: str | None = None) -> int:
        q = select(func.count()).select_from(ModelRegistryEntry)
        if model_type:
            q = q.where(ModelRegistryEntry.model_type == model_type)
        if status:
            q = q.where(ModelRegistryEntry.status == status)
        return (await self.session.execute(q)).scalar() or 0

    async def update_entry(
        self, entry_id: int,
        description: str | None = None,
        framework: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelRegistryEntry | None:
        entry = await self.get_entry(entry_id)
        if not entry:
            return None
        if description is not None:
            entry.description = description
        if framework is not None:
            entry.framework = framework
        if status is not None:
            entry.status = status
        if tags is not None:
            entry.tags_json = json.dumps(tags)
        if metadata is not None:
            entry.metadata_json = json.dumps(metadata)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    # ── Version CRUD ──

    async def create_version(
        self, entry_id: int, version: str,
        description: str | None = None,
        source: str | None = None,
        changelog: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelRegistryVersion:
        v = ModelRegistryVersion(
            entry_id=entry_id,
            version=version,
            description=description,
            source=source,
            changelog=changelog,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(v)
        await self.session.flush()
        await self.session.refresh(v)
        return v

    async def get_version(self, version_id: int) -> ModelRegistryVersion | None:
        return await self.session.get(ModelRegistryVersion, version_id)

    async def get_versions(
        self, entry_id: int, limit: int = 50, offset: int = 0,
    ) -> list[ModelRegistryVersion]:
        r = await self.session.execute(
            select(ModelRegistryVersion)
            .where(ModelRegistryVersion.entry_id == entry_id)
            .order_by(desc(ModelRegistryVersion.created_at))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    async def count_versions(self, entry_id: int) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(ModelRegistryVersion)
            .where(ModelRegistryVersion.entry_id == entry_id)
        )
        return r.scalar() or 0

    async def update_version(
        self, version_id: int,
        description: str | None = None,
        source: str | None = None,
        changelog: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelRegistryVersion | None:
        v = await self.get_version(version_id)
        if not v:
            return None
        if description is not None:
            v.description = description
        if source is not None:
            v.source = source
        if changelog is not None:
            v.changelog = changelog
        if status is not None:
            v.status = status
        if metadata is not None:
            v.metadata_json = json.dumps(metadata)
        await self.session.flush()
        await self.session.refresh(v)
        return v

    # ── Active Model Selection ──

    async def set_active_version(self, version_id: int) -> ModelRegistryVersion | None:
        v = await self.get_version(version_id)
        if not v:
            return None

        r = await self.session.execute(
            select(ModelRegistryVersion).where(
                ModelRegistryVersion.entry_id == v.entry_id,
                ModelRegistryVersion.is_active == True,
            )
        )
        for old_active in r.scalars().all():
            old_active.is_active = False

        v.is_active = True
        await self.session.flush()
        await self.session.refresh(v)
        return v

    async def get_active_version(self, entry_id: int) -> ModelRegistryVersion | None:
        r = await self.session.execute(
            select(ModelRegistryVersion).where(
                ModelRegistryVersion.entry_id == entry_id,
                ModelRegistryVersion.is_active == True,
            )
        )
        return r.scalar_one_or_none()

    async def get_active_version_by_entry_name(self, entry_name: str) -> ModelRegistryVersion | None:
        entry = await self.get_entry_by_name(entry_name)
        if not entry:
            return None
        return await self.get_active_version(entry.id)

    # ── Training Runs ──

    async def create_training_run(
        self, version_id: int,
        run_id: str | None = None,
        dataset_info: dict[str, Any] | None = None,
        hyperparameters: dict[str, Any] | None = None,
        training_duration_seconds: float | None = None,
        status: str = "completed",
        metrics: dict[str, Any] | None = None,
        artifact_path: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        notes: str | None = None,
    ) -> ModelTrainingRun:
        tr = ModelTrainingRun(
            version_id=version_id,
            run_id=run_id,
            dataset_info_json=json.dumps(dataset_info) if dataset_info else None,
            hyperparameters_json=json.dumps(hyperparameters) if hyperparameters else None,
            training_duration_seconds=training_duration_seconds,
            status=status,
            metrics_json=json.dumps(metrics) if metrics else None,
            artifact_path=artifact_path,
            started_at=started_at,
            completed_at=completed_at,
            notes=notes,
        )
        self.session.add(tr)
        await self.session.flush()
        await self.session.refresh(tr)
        return tr

    async def get_training_run(self, run_id: int) -> ModelTrainingRun | None:
        return await self.session.get(ModelTrainingRun, run_id)

    async def list_training_runs(
        self, version_id: int, limit: int = 50, offset: int = 0,
    ) -> list[ModelTrainingRun]:
        r = await self.session.execute(
            select(ModelTrainingRun)
            .where(ModelTrainingRun.version_id == version_id)
            .order_by(desc(ModelTrainingRun.created_at))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    async def count_training_runs(self, version_id: int) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(ModelTrainingRun)
            .where(ModelTrainingRun.version_id == version_id)
        )
        return r.scalar() or 0

    # ── Metrics ──

    async def record_metric(
        self, version_id: int, metric_name: str, metric_value: float,
        metric_type: str = "float",
        dataset_type: str = "validation",
    ) -> ModelMetric:
        m = ModelMetric(
            version_id=version_id,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_type=metric_type,
            dataset_type=dataset_type,
        )
        self.session.add(m)
        await self.session.flush()
        await self.session.refresh(m)
        return m

    async def get_metrics(
        self, version_id: int,
        metric_name: str | None = None,
        dataset_type: str | None = None,
    ) -> list[ModelMetric]:
        q = select(ModelMetric).where(ModelMetric.version_id == version_id)
        if metric_name:
            q = q.where(ModelMetric.metric_name == metric_name)
        if dataset_type:
            q = q.where(ModelMetric.dataset_type == dataset_type)
        q = q.order_by(ModelMetric.metric_name)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    # ── Deployment & Rollback ──

    async def deploy(
        self, version_id: int, environment: str,
        deployed_by: str | None = None,
        notes: str | None = None,
    ) -> ModelRegistryDeployment:
        v = await self.get_version(version_id)
        if not v:
            raise ValueError(f"Version {version_id} not found")

        r = await self.session.execute(
            select(ModelRegistryDeployment).where(
                ModelRegistryDeployment.environment == environment,
                ModelRegistryDeployment.status == "active",
            )
        )
        current_active = r.scalar_one_or_none()

        prev_version_id = None
        if current_active:
            prev_version_id = current_active.version_id
            current_active.status = "inactive"
            current_active.rolled_back_at = datetime.now(timezone.utc)

        r2 = await self.session.execute(
            select(ModelRegistryDeployment).where(
                ModelRegistryDeployment.version_id == version_id,
                ModelRegistryDeployment.environment == environment,
            )
        )
        existing = r2.scalar_one_or_none()

        if existing:
            existing.status = "active"
            existing.deployed_by = deployed_by
            existing.deployed_at = datetime.now(timezone.utc)
            existing.rolled_back_at = None
            existing.rollback_to_version_id = prev_version_id
            existing.notes = notes
            dep = existing
        else:
            dep = ModelRegistryDeployment(
                version_id=version_id,
                environment=environment,
                deployed_by=deployed_by,
                notes=notes,
                rollback_to_version_id=prev_version_id,
            )
            self.session.add(dep)

        await self.session.flush()
        await self.session.refresh(dep)
        return dep

    async def rollback(
        self, environment: str,
        rolled_by: str | None = None,
    ) -> ModelRegistryDeployment | None:
        r = await self.session.execute(
            select(ModelRegistryDeployment).where(
                ModelRegistryDeployment.environment == environment,
                ModelRegistryDeployment.status == "active",
            )
        )
        active_dep = r.scalar_one_or_none()
        if not active_dep or not active_dep.rollback_to_version_id:
            return None

        rollback_version_id = active_dep.rollback_to_version_id
        active_dep.status = "rolled_back"
        active_dep.rolled_back_at = datetime.now(timezone.utc)

        r2 = await self.session.execute(
            select(ModelRegistryDeployment).where(
                ModelRegistryDeployment.version_id == rollback_version_id,
                ModelRegistryDeployment.environment == environment,
            )
        )
        prev = r2.scalar_one_or_none()

        if prev:
            prev.status = "active"
            prev.deployed_at = datetime.now(timezone.utc)
            prev.deployed_by = rolled_by
            prev.rolled_back_at = None
            dep = prev
        else:
            v = await self.get_version(rollback_version_id)
            if not v:
                return None
            dep = ModelRegistryDeployment(
                version_id=rollback_version_id,
                environment=environment,
                deployed_by=rolled_by,
                status="active",
            )
            self.session.add(dep)

        await self.session.flush()
        await self.session.refresh(dep)
        return dep

    async def get_active_deployment(self, environment: str) -> ModelRegistryDeployment | None:
        r = await self.session.execute(
            select(ModelRegistryDeployment).where(
                ModelRegistryDeployment.environment == environment,
                ModelRegistryDeployment.status == "active",
            )
        )
        return r.scalar_one_or_none()

    async def get_deployments(self, version_id: int) -> list[ModelRegistryDeployment]:
        r = await self.session.execute(
            select(ModelRegistryDeployment).where(ModelRegistryDeployment.version_id == version_id)
            .order_by(desc(ModelRegistryDeployment.deployed_at))
        )
        return list(r.scalars().all())

    async def get_deployment_history(self, environment: str) -> list[ModelRegistryDeployment]:
        r = await self.session.execute(
            select(ModelRegistryDeployment).where(ModelRegistryDeployment.environment == environment)
            .order_by(desc(ModelRegistryDeployment.deployed_at))
        )
        return list(r.scalars().all())

    # ── Compare ──

    async def compare_versions(self, version_ids: list[int]) -> list[dict[str, Any]]:
        results = []
        for vid in version_ids:
            v = await self.get_version(vid)
            if not v:
                continue
            metrics = await self.get_metrics(vid)
            deployments = await self.get_deployments(vid)
            training_runs = await self.list_training_runs(vid, limit=1)
            results.append({
                "version_id": v.id,
                "entry_id": v.entry_id,
                "version": v.version,
                "status": v.status,
                "is_active": v.is_active,
                "source": v.source,
                "changelog": v.changelog,
                "metrics": [{"name": m.metric_name, "value": m.metric_value, "dataset": m.dataset_type} for m in metrics],
                "deployments": [{"env": d.environment, "status": d.status} for d in deployments],
                "latest_training_run": training_runs[0].metrics_json if training_runs else None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            })
        return results
