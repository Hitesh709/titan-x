import json
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.experiment_manager import (
    Experiment,
    ExperimentArtifact,
    ExperimentChart,
    ExperimentMetric,
    ExperimentParameter,
    ExperimentTag,
)


class ExperimentManagerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Experiment CRUD ──

    async def create_experiment(
        self, name: str,
        description: str | None = None,
        experiment_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
    ) -> Experiment:
        eid = experiment_id or str(uuid_lib.uuid4())
        exp = Experiment(
            experiment_id=eid,
            name=name, description=description,
            status="running",
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(exp)
        await self.session.flush()
        await self.session.refresh(exp)

        if tags:
            for k, v in tags.items():
                self.session.add(ExperimentTag(experiment_id=exp.id, key=k, value=v))
            await self.session.flush()

        return exp

    async def get_experiment(self, experiment_id: int) -> Experiment | None:
        return await self.session.get(Experiment, experiment_id)

    async def get_experiment_by_uuid(self, experiment_id: str) -> Experiment | None:
        r = await self.session.execute(
            select(Experiment).where(Experiment.experiment_id == experiment_id)
        )
        return r.scalar_one_or_none()

    async def list_experiments(
        self, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[Experiment]:
        q = select(Experiment)
        if status:
            q = q.where(Experiment.status == status)
        q = q.order_by(desc(Experiment.created_at)).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def update_experiment_status(
        self, experiment_id: int, status: str,
    ) -> Experiment | None:
        exp = await self.get_experiment(experiment_id)
        if not exp:
            return None
        exp.status = status
        if status in ("completed", "failed", "aborted"):
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            exp.completed_at = now
            if exp.started_at:
                exp.duration_seconds = (now - exp.started_at).total_seconds()
        await self.session.flush()
        await self.session.refresh(exp)
        return exp

    async def delete_experiment(self, experiment_id: int) -> bool:
        exp = await self.get_experiment(experiment_id)
        if not exp:
            return False
        await self.session.delete(exp)
        await self.session.flush()
        return True

    # ── Parameters ──

    async def log_parameter(
        self, experiment_id: int, key: str, value: Any,
        param_type: str | None = None,
    ) -> ExperimentParameter:
        if param_type is None:
            param_type = type(value).__name__
        ep = ExperimentParameter(
            experiment_id=experiment_id,
            key=key, value=str(value),
            param_type=param_type,
        )
        self.session.add(ep)
        await self.session.flush()
        await self.session.refresh(ep)
        return ep

    async def log_parameters(
        self, experiment_id: int, params: dict[str, Any],
    ) -> list[ExperimentParameter]:
        results: list[ExperimentParameter] = []
        for k, v in params.items():
            ep = ExperimentParameter(
                experiment_id=experiment_id, key=k,
                value=str(v), param_type=type(v).__name__,
            )
            self.session.add(ep)
            results.append(ep)
        await self.session.flush()
        for ep in results:
            await self.session.refresh(ep)
        return results

    async def get_parameters(self, experiment_id: int) -> list[ExperimentParameter]:
        r = await self.session.execute(
            select(ExperimentParameter)
            .where(ExperimentParameter.experiment_id == experiment_id)
            .order_by(ExperimentParameter.key)
        )
        return list(r.scalars().all())

    # ── Metrics ──

    async def log_metric(
        self, experiment_id: int, key: str, value: float,
        step: int | None = None, epoch: int | None = None,
    ) -> ExperimentMetric:
        em = ExperimentMetric(
            experiment_id=experiment_id, key=key, value=value,
            step=step, epoch=epoch,
        )
        self.session.add(em)
        await self.session.flush()
        await self.session.refresh(em)
        await self._update_best_metric(experiment_id, key, value)
        return em

    async def log_metrics(
        self, experiment_id: int, metrics: dict[str, float],
        step: int | None = None, epoch: int | None = None,
    ) -> list[ExperimentMetric]:
        results: list[ExperimentMetric] = []
        for k, v in metrics.items():
            em = ExperimentMetric(
                experiment_id=experiment_id, key=k, value=v,
                step=step, epoch=epoch,
            )
            self.session.add(em)
            results.append(em)
        await self.session.flush()
        for em in results:
            await self.session.refresh(em)
        return results

    async def get_metrics(
        self, experiment_id: int, key: str | None = None,
    ) -> list[ExperimentMetric]:
        q = select(ExperimentMetric).where(ExperimentMetric.experiment_id == experiment_id)
        if key:
            q = q.where(ExperimentMetric.key == key)
        q = q.order_by(ExperimentMetric.step, ExperimentMetric.created_at)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def get_metric_history(
        self, experiment_id: int, key: str,
    ) -> list[ExperimentMetric]:
        return await self.get_metrics(experiment_id, key=key)

    async def _update_best_metric(self, experiment_id: int, key: str, value: float) -> None:
        exp = await self.get_experiment(experiment_id)
        if not exp:
            return

        direction = exp.best_metric_direction or "max"
        current_best = exp.best_metric_value if exp.best_metric_name == key else None

        is_better = False
        if current_best is None:
            is_better = True
        elif direction == "max" and value > current_best:
            is_better = True
        elif direction == "min" and value < current_best:
            is_better = True

        if is_better:
            exp.best_metric_name = key
            exp.best_metric_value = value

    async def set_best_metric_direction(
        self, experiment_id: int, key: str, direction: str,
    ) -> Experiment | None:
        exp = await self.get_experiment(experiment_id)
        if not exp:
            return None
        exp.best_metric_name = key
        exp.best_metric_direction = direction

        r = await self.session.execute(
            select(func.max(ExperimentMetric.value))
            .where(
                ExperimentMetric.experiment_id == experiment_id,
                ExperimentMetric.key == key,
            )
        )
        max_val = r.scalar()
        if max_val is not None:
            if direction == "max":
                exp.best_metric_value = max_val
            else:
                r2 = await self.session.execute(
                    select(func.min(ExperimentMetric.value))
                    .where(
                        ExperimentMetric.experiment_id == experiment_id,
                        ExperimentMetric.key == key,
                    )
                )
                min_val = r2.scalar()
                exp.best_metric_value = min_val

        await self.session.flush()
        await self.session.refresh(exp)
        return exp

    # ── Artifacts ──

    async def log_artifact(
        self, experiment_id: int, name: str,
        description: str | None = None,
        artifact_type: str = "file",
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        uri: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExperimentArtifact:
        art = ExperimentArtifact(
            experiment_id=experiment_id, name=name,
            description=description, artifact_type=artifact_type,
            file_path=file_path, file_size_bytes=file_size_bytes,
            uri=uri, metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(art)
        await self.session.flush()
        await self.session.refresh(art)
        return art

    async def get_artifacts(
        self, experiment_id: int, artifact_type: str | None = None,
    ) -> list[ExperimentArtifact]:
        q = select(ExperimentArtifact).where(ExperimentArtifact.experiment_id == experiment_id)
        if artifact_type:
            q = q.where(ExperimentArtifact.artifact_type == artifact_type)
        q = q.order_by(ExperimentArtifact.name)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    # ── Charts ──

    async def log_chart(
        self, experiment_id: int, name: str,
        chart_type: str = "line",
        chart_config: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExperimentChart:
        ch = ExperimentChart(
            experiment_id=experiment_id, name=name,
            chart_type=chart_type,
            chart_config_json=json.dumps(chart_config) if chart_config else None,
            data_json=json.dumps(data) if data else None,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(ch)
        await self.session.flush()
        await self.session.refresh(ch)
        return ch

    async def get_charts(self, experiment_id: int) -> list[ExperimentChart]:
        r = await self.session.execute(
            select(ExperimentChart)
            .where(ExperimentChart.experiment_id == experiment_id)
            .order_by(ExperimentChart.name)
        )
        return list(r.scalars().all())

    # ── Tags ──

    async def add_tag(self, experiment_id: int, key: str, value: str) -> ExperimentTag:
        tag = ExperimentTag(experiment_id=experiment_id, key=key, value=value)
        self.session.add(tag)
        await self.session.flush()
        await self.session.refresh(tag)
        return tag

    async def get_tags(self, experiment_id: int) -> list[ExperimentTag]:
        r = await self.session.execute(
            select(ExperimentTag)
            .where(ExperimentTag.experiment_id == experiment_id)
            .order_by(ExperimentTag.key)
        )
        return list(r.scalars().all())

    async def find_by_tag(self, key: str, value: str) -> list[Experiment]:
        r = await self.session.execute(
            select(Experiment).join(
                ExperimentTag, Experiment.id == ExperimentTag.experiment_id,
            ).where(
                ExperimentTag.key == key,
                ExperimentTag.value == value,
            ).order_by(desc(Experiment.created_at))
        )
        return list(r.scalars().all())

    # ── Best Model Selection ──

    async def find_best_experiment(
        self, metric_name: str,
        direction: str = "max",
        status: str | None = "completed",
        tags: dict[str, str] | None = None,
    ) -> Experiment | None:
        exp_ids: list[int] | None = None
        if tags:
            r = await self.session.execute(
                select(ExperimentTag.experiment_id).where(
                    ExperimentTag.key.in_(list(tags.keys())),
                    ExperimentTag.value.in_(list(tags.values())),
                )
            )
            exp_ids = list(set(r.scalars().all()))
            if not exp_ids:
                return None

        q = select(Experiment)
        if status:
            q = q.where(Experiment.status == status)
        if exp_ids is not None:
            q = q.where(Experiment.id.in_(exp_ids))

        r = await self.session.execute(q)
        experiments = list(r.scalars().all())

        if not experiments:
            return None

        candidates: list[tuple[Experiment, float]] = []
        for exp in experiments:
            metric_r = await self.session.execute(
                select(ExperimentMetric.value)
                .where(
                    ExperimentMetric.experiment_id == exp.id,
                    ExperimentMetric.key == metric_name,
                )
                .order_by(desc(ExperimentMetric.value) if direction == "max" else ExperimentMetric.value)
                .limit(1)
            )
            best_val = metric_r.scalar()
            if best_val is not None:
                candidates.append((exp, best_val))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1], reverse=(direction == "max"))
        return candidates[0][0]

    async def get_experiment_summary(self, experiment_id: int) -> dict[str, Any] | None:
        exp = await self.get_experiment(experiment_id)
        if not exp:
            return None
        params = await self.get_parameters(experiment_id)
        metrics = await self.get_metrics(experiment_id)
        artifacts = await self.get_artifacts(experiment_id)
        charts = await self.get_charts(experiment_id)
        tags = await self.get_tags(experiment_id)

        metric_keys = set(m.key for m in metrics)
        metric_summary = {}
        for key in metric_keys:
            vals = [m.value for m in metrics if m.key == key]
            metric_summary[key] = {
                "min": min(vals), "max": max(vals),
                "mean": sum(vals) / len(vals),
                "count": len(vals),
            }

        return {
            "experiment": {
                "id": exp.id, "experiment_id": exp.experiment_id,
                "name": exp.name, "description": exp.description,
                "status": exp.status,
                "best_metric_name": exp.best_metric_name,
                "best_metric_value": exp.best_metric_value,
                "duration_seconds": exp.duration_seconds,
                "started_at": exp.started_at.isoformat() if exp.started_at else None,
                "completed_at": exp.completed_at.isoformat() if exp.completed_at else None,
                "created_at": exp.created_at.isoformat() if exp.created_at else None,
            },
            "parameters": {p.key: {"value": p.value, "type": p.param_type} for p in params},
            "metrics": metric_summary,
            "artifact_count": len(artifacts),
            "chart_count": len(charts),
            "tags": {t.key: t.value for t in tags},
        }
