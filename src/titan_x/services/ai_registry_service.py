from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.ai_registry import AIModelRegistry, ModelDeployment


class AIModelRegistryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register(
        self,
        name: str,
        version: str,
        model_type: str,
        description: str | None = None,
        model_metadata_json: str | None = None,
        source: str | None = None,
        metrics_json: str | None = None,
    ) -> AIModelRegistry:
        model = AIModelRegistry(
            name=name,
            version=version,
            model_type=model_type,
            description=description,
            model_metadata_json=model_metadata_json,
            source=source,
            metrics_json=metrics_json,
            status="draft",
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model

    async def get(self, model_id: int) -> AIModelRegistry | None:
        return await self.session.get(AIModelRegistry, model_id)

    async def get_by_name(self, name: str) -> list[AIModelRegistry]:
        result = await self.session.execute(
            select(AIModelRegistry).where(AIModelRegistry.name == name).order_by(AIModelRegistry.created_at.desc())
        )
        return list(result.scalars().all())

    async def list(
        self,
        model_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AIModelRegistry], int]:
        q = select(AIModelRegistry)
        count_q = select(AIModelRegistry)
        if model_type:
            q = q.where(AIModelRegistry.model_type == model_type)
            count_q = count_q.where(AIModelRegistry.model_type == model_type)
        if status:
            q = q.where(AIModelRegistry.status == status)
            count_q = count_q.where(AIModelRegistry.status == status)
        q = q.order_by(AIModelRegistry.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(q)
        rows = list(result.scalars().unique().all())
        count_result = await self.session.execute(count_q)
        total = len(list(count_result.scalars().all()))
        return rows, total

    async def update(
        self,
        model_id: int,
        description: str | None = None,
        model_metadata_json: str | None = None,
        metrics_json: str | None = None,
        source: str | None = None,
    ) -> AIModelRegistry | None:
        model = await self.get(model_id)
        if model is None:
            return None
        if description is not None:
            model.description = description
        if model_metadata_json is not None:
            model.model_metadata_json = model_metadata_json
        if metrics_json is not None:
            model.metrics_json = metrics_json
        if source is not None:
            model.source = source
        await self.session.flush()
        return model

    async def change_status(self, model_id: int, status: str) -> AIModelRegistry | None:
        valid = ("draft", "active", "archived", "deprecated")
        if status not in valid:
            raise ValueError(f"Invalid status: {status}. Valid: {valid}")
        model = await self.get(model_id)
        if model is None:
            return None
        model.status = status
        await self.session.flush()
        return model

    async def deploy(
        self,
        model_id: int,
        environment: str,
        deployed_by: str | None = None,
    ) -> ModelDeployment:
        if environment not in ("dev", "staging", "production"):
            raise ValueError("Environment must be dev, staging, or production")

        result = await self.session.execute(
            select(ModelDeployment).where(
                ModelDeployment.model_id == model_id,
                ModelDeployment.environment == environment,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.status = "active"
            existing.deployed_at = datetime.now(timezone.utc)
            existing.deployed_by = deployed_by
            deployment = existing
        else:
            deployment = ModelDeployment(
                model_id=model_id,
                environment=environment,
                deployed_by=deployed_by,
            )
            self.session.add(deployment)

        await self.session.flush()
        await self.session.refresh(deployment)
        return deployment

    async def get_deployments(self, model_id: int) -> list[ModelDeployment]:
        result = await self.session.execute(
            select(ModelDeployment).where(ModelDeployment.model_id == model_id)
        )
        return list(result.scalars().all())

    async def compare(self, model_ids: list[int]) -> list[dict]:
        results = []
        for mid in model_ids:
            model = await self.get(mid)
            if model:
                deployments = await self.get_deployments(mid)
                results.append({
                    "id": model.id,
                    "name": model.name,
                    "version": model.version,
                    "model_type": model.model_type,
                    "status": model.status,
                    "metrics_json": model.metrics_json,
                    "deployments": [
                        {"env": d.environment, "status": d.status} for d in deployments
                    ],
                    "created_at": model.created_at.isoformat() if model.created_at else None,
                })
        return results
