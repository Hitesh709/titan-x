"""Pipeline, lineage, and metadata mixins for :class:`DataLakeService`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from titan_x.models.data_lake import (
    DataLakeLineage,
    DataLakeMetadata,
    DataLakePipeline,
)
from titan_x.services.datalake.constants import VALID_TRANSFORMATIONS, _validate_layer


class PipelineMixin:
    async def create_pipeline(
        self,
        name: str,
        source_layer: str,
        target_layer: str,
        source_catalog_id: int | None = None,
        target_catalog_id: int | None = None,
        pipeline_type: str = "transform",
        config_json: str | None = None,
    ) -> DataLakePipeline:
        _validate_layer(source_layer)
        _validate_layer(target_layer)
        entry = DataLakePipeline(
            name=name,
            source_layer=source_layer,
            target_layer=target_layer,
            source_catalog_id=source_catalog_id,
            target_catalog_id=target_catalog_id,
            pipeline_type=pipeline_type,
            config_json=config_json,
            status="pending",
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def start_pipeline(self, pipeline_id: int) -> DataLakePipeline | None:
        entry = await self._get_pipeline(pipeline_id)
        if not entry:
            return None
        entry.status = "running"
        entry.started_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def complete_pipeline(
        self,
        pipeline_id: int,
        rows_read: int = 0,
        rows_written: int = 0,
        rows_failed: int = 0,
        error_message: str | None = None,
    ) -> DataLakePipeline | None:
        entry = await self._get_pipeline(pipeline_id)
        if not entry:
            return None
        entry.status = "failed" if error_message else "completed"
        entry.completed_at = datetime.utcnow()
        entry.rows_read = rows_read
        entry.rows_written = rows_written
        entry.rows_failed = rows_failed
        entry.error_message = error_message
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def list_pipelines(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[DataLakePipeline]:
        stmt = select(DataLakePipeline).order_by(
            DataLakePipeline.started_at.desc().nullslast(),
        )
        if status:
            stmt = stmt.where(DataLakePipeline.status == status)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pipeline(self, pipeline_id: int) -> DataLakePipeline | None:
        return await self._get_pipeline(pipeline_id)


class LineageMixin:
    async def record_lineage(
        self,
        source_catalog_id: int,
        target_catalog_id: int,
        transformation: str,
        pipeline_id: int | None = None,
        source_version: str | None = None,
        target_version: str | None = None,
    ) -> DataLakeLineage:
        if transformation not in VALID_TRANSFORMATIONS:
            raise ValueError(
                f"Invalid transformation '{transformation}'. Must be one of {VALID_TRANSFORMATIONS}"
            )
        entry = DataLakeLineage(
            source_catalog_id=source_catalog_id,
            target_catalog_id=target_catalog_id,
            pipeline_id=pipeline_id,
            transformation=transformation,
            source_version=source_version,
            target_version=target_version,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def get_downstream(
        self,
        catalog_id: int,
    ) -> list[DataLakeLineage]:
        result = await self.session.execute(
            select(DataLakeLineage)
            .where(DataLakeLineage.source_catalog_id == catalog_id)
            .options(selectinload(DataLakeLineage.target_dataset))
            .order_by(DataLakeLineage.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_upstream(
        self,
        catalog_id: int,
    ) -> list[DataLakeLineage]:
        result = await self.session.execute(
            select(DataLakeLineage)
            .where(DataLakeLineage.target_catalog_id == catalog_id)
            .options(selectinload(DataLakeLineage.source_dataset))
            .order_by(DataLakeLineage.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_lineage_graph(
        self,
        catalog_id: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return full lineage as a graph with nodes and edges."""
        nodes: dict[int, dict] = {}
        edges: list[dict] = []

        async def _walk_up(cid: int) -> None:
            upstream = await self.get_upstream(cid)
            for ln in upstream:
                if ln.source_dataset:
                    nodes[ln.source_dataset.id] = {
                        "id": ln.source_dataset.id,
                        "name": ln.source_dataset.name,
                        "layer": ln.source_dataset.layer,
                    }
                edges.append(
                    {
                        "source": ln.source_catalog_id,
                        "target": ln.target_catalog_id,
                        "transformation": ln.transformation,
                    }
                )
                if ln.source_dataset:
                    await _walk_up(ln.source_dataset.id)

        async def _walk_down(cid: int) -> None:
            downstream = await self.get_downstream(cid)
            for ln in downstream:
                if ln.target_dataset:
                    nodes[ln.target_dataset.id] = {
                        "id": ln.target_dataset.id,
                        "name": ln.target_dataset.name,
                        "layer": ln.target_dataset.layer,
                    }
                edges.append(
                    {
                        "source": ln.source_catalog_id,
                        "target": ln.target_catalog_id,
                        "transformation": ln.transformation,
                    }
                )
                if ln.target_dataset:
                    await _walk_down(ln.target_dataset.id)

        root = await self.get_dataset(dataset_id=catalog_id)
        if root:
            nodes[root.id] = {
                "id": root.id,
                "name": root.name,
                "layer": root.layer,
            }

        await _walk_up(catalog_id)
        await _walk_down(catalog_id)

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
        }


class MetadataMixin:
    async def set_metadata(
        self,
        catalog_id: int,
        metric_name: str,
        metric_value: str,
        metric_type: str = "string",
    ) -> DataLakeMetadata:
        entry = DataLakeMetadata(
            catalog_id=catalog_id,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_type=metric_type,
            computed_at=datetime.utcnow(),
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def get_metadata(
        self,
        catalog_id: int,
        metric_name: str | None = None,
    ) -> list[DataLakeMetadata]:
        stmt = select(DataLakeMetadata).where(
            DataLakeMetadata.catalog_id == catalog_id,
        )
        if metric_name:
            stmt = stmt.where(DataLakeMetadata.metric_name == metric_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
