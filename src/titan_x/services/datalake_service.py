"""Data Lake management service.

Orchestrates dataset registration, versioning, schema management,
pipeline execution, lineage tracking, archival, and metadata across
the 8 data-lake layers: raw, validated, normalized, features,
predictions, archives, metadata, staging.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.models.data_lake import (
    DATALAKE_LAYERS,
    DataLakeArchive,
    DataLakeCatalog,
    DataLakeDiff,
    DataLakeIngestionRun,
    DataLakeLineage,
    DataLakeMetadata,
    DataLakePipeline,
    DataLakeSchema,
    DataLakeSnapshot,
    DataLakeSource,
    DataLakeStorageRecord,
    DataLakeVersion,
)
from titan_x.services import datalake_storage as storage


# ── Layer validators ─────────────────────────────────────────────────────────

VALID_TRANSFORMATIONS = (
    "ingest", "validate", "normalize", "feature_engineer",
    "predict", "archive", "restore", "copy", "merge", "filter",
)

PIPELINE_STATUSES = ("pending", "running", "completed", "failed", "cancelled")


def _validate_layer(layer: str) -> None:
    if layer not in DATALAKE_LAYERS:
        raise ValueError(
            f"Invalid layer '{layer}'. Must be one of {DATALAKE_LAYERS}"
        )


def _serialize_dt(val: Any) -> str | None:
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


# ── Service ──────────────────────────────────────────────────────────────────


class DataLakeService:
    """Service for managing the data lake catalog, storage, and pipelines."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Catalog ──────────────────────────────────────────────────────────

    async def register_dataset(
        self,
        name: str,
        layer: str,
        storage_path: str | None = None,
        format: str = "parquet",
        description: str | None = None,
        tags: str | None = None,
        partition_columns: str | None = None,
        source: str | None = None,
    ) -> DataLakeCatalog:
        _validate_layer(layer)
        if not storage_path:
            storage_path = storage._partition_path(layer, name)

        existing = await self._find_catalog(name, layer)
        if existing:
            return existing

        entry = DataLakeCatalog(
            name=name,
            layer=layer,
            storage_path=storage_path,
            format=format,
            description=description,
            tags=tags,
            partition_columns=partition_columns,
            source=source,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def get_dataset(
        self, dataset_id: int | None = None,
        name: str | None = None, layer: str | None = None,
    ) -> DataLakeCatalog | None:
        if dataset_id:
            result = await self.session.execute(
                select(DataLakeCatalog).where(DataLakeCatalog.id == dataset_id)
            )
            return result.scalar_one_or_none()
        if name and layer:
            return await self._find_catalog(name, layer)
        return None

    async def list_datasets(
        self, layer: str | None = None, active_only: bool = True,
    ) -> list[DataLakeCatalog]:
        stmt = select(DataLakeCatalog)
        if layer:
            _validate_layer(layer)
            stmt = stmt.where(DataLakeCatalog.layer == layer)
        if active_only:
            stmt = stmt.where(DataLakeCatalog.is_active.is_(True))
        stmt = stmt.order_by(DataLakeCatalog.layer, DataLakeCatalog.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_dataset(
        self, dataset_id: int, **kwargs: Any,
    ) -> DataLakeCatalog | None:
        entry = await self.get_dataset(dataset_id=dataset_id)
        if not entry:
            return None
        for k, v in kwargs.items():
            if hasattr(entry, k) and v is not None:
                setattr(entry, k, v)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_dataset(
        self, dataset_id: int, remove_files: bool = False,
    ) -> bool:
        entry = await self.get_dataset(dataset_id=dataset_id)
        if not entry:
            return False
        if remove_files:
            storage.delete_dataset(entry.layer, entry.name)
        await self.session.delete(entry)
        await self.session.commit()
        return True

    # ── Schema ───────────────────────────────────────────────────────────

    async def register_schema(
        self, catalog_id: int, schema_def: dict[str, Any],
        version: str = "1.0.0",
        created_by: str | None = None,
    ) -> DataLakeSchema:
        entry = DataLakeSchema(
            catalog_id=catalog_id,
            version=version,
            schema_definition=json.dumps(schema_def),
            columns=json.dumps(list(schema_def.keys())) if isinstance(schema_def, dict) else None,
            created_by=created_by,
        )
        self.session.add(entry)
        # Update catalog schema version
        cat = await self.get_dataset(dataset_id=catalog_id)
        if cat:
            cat.schema_version = version
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def get_schema(
        self, catalog_id: int, version: str | None = None,
    ) -> DataLakeSchema | None:
        stmt = select(DataLakeSchema).where(
            DataLakeSchema.catalog_id == catalog_id,
        )
        if version:
            stmt = stmt.where(DataLakeSchema.version == version)
        else:
            stmt = stmt.where(DataLakeSchema.is_active.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_schemas(self, catalog_id: int) -> list[DataLakeSchema]:
        result = await self.session.execute(
            select(DataLakeSchema)
            .where(DataLakeSchema.catalog_id == catalog_id)
            .order_by(DataLakeSchema.version.desc())
        )
        return list(result.scalars().all())

    # ── Versioning ───────────────────────────────────────────────────────

    async def create_version(
        self, catalog_id: int, version: str,
        storage_path: str,
        row_count: int = 0,
        checksum: str | None = None,
        metadata_json: str | None = None,
        parent_version: str | None = None,
    ) -> DataLakeVersion:
        entry = DataLakeVersion(
            catalog_id=catalog_id,
            version=version,
            storage_path=storage_path,
            row_count=row_count,
            checksum=checksum,
            metadata_json=metadata_json,
            parent_version=parent_version,
        )
        self.session.add(entry)

        cat = await self.get_dataset(dataset_id=catalog_id)
        if cat and row_count:
            cat.row_count = row_count
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def list_versions(self, catalog_id: int) -> list[DataLakeVersion]:
        result = await self.session.execute(
            select(DataLakeVersion)
            .where(DataLakeVersion.catalog_id == catalog_id)
            .order_by(DataLakeVersion.version.desc())
        )
        return list(result.scalars().all())

    async def get_version(
        self, catalog_id: int, version: str,
    ) -> DataLakeVersion | None:
        result = await self.session.execute(
            select(DataLakeVersion).where(
                DataLakeVersion.catalog_id == catalog_id,
                DataLakeVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    # ── Pipeline ─────────────────────────────────────────────────────────

    async def create_pipeline(
        self, name: str,
        source_layer: str, target_layer: str,
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
        self, pipeline_id: int,
        rows_read: int = 0, rows_written: int = 0, rows_failed: int = 0,
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
        self, status: str | None = None, limit: int = 50,
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

    # ── Lineage ──────────────────────────────────────────────────────────

    async def record_lineage(
        self, source_catalog_id: int, target_catalog_id: int,
        transformation: str,
        pipeline_id: int | None = None,
        source_version: str | None = None,
        target_version: str | None = None,
    ) -> DataLakeLineage:
        if transformation not in VALID_TRANSFORMATIONS:
            raise ValueError(
                f"Invalid transformation '{transformation}'. "
                f"Must be one of {VALID_TRANSFORMATIONS}"
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
        self, catalog_id: int,
    ) -> list[DataLakeLineage]:
        result = await self.session.execute(
            select(DataLakeLineage)
            .where(DataLakeLineage.source_catalog_id == catalog_id)
            .options(selectinload(DataLakeLineage.target_dataset))
            .order_by(DataLakeLineage.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_upstream(
        self, catalog_id: int,
    ) -> list[DataLakeLineage]:
        result = await self.session.execute(
            select(DataLakeLineage)
            .where(DataLakeLineage.target_catalog_id == catalog_id)
            .options(selectinload(DataLakeLineage.source_dataset))
            .order_by(DataLakeLineage.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_lineage_graph(
        self, catalog_id: int,
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
                edges.append({
                    "source": ln.source_catalog_id,
                    "target": ln.target_catalog_id,
                    "transformation": ln.transformation,
                })
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
                edges.append({
                    "source": ln.source_catalog_id,
                    "target": ln.target_catalog_id,
                    "transformation": ln.transformation,
                })
                if ln.target_dataset:
                    await _walk_down(ln.target_dataset.id)

        root = await self.get_dataset(dataset_id=catalog_id)
        if root:
            nodes[root.id] = {
                "id": root.id, "name": root.name, "layer": root.layer,
            }

        await _walk_up(catalog_id)
        await _walk_down(catalog_id)

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    # ── Metadata ─────────────────────────────────────────────────────────

    async def set_metadata(
        self, catalog_id: int, metric_name: str,
        metric_value: str, metric_type: str = "string",
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
        self, catalog_id: int, metric_name: str | None = None,
    ) -> list[DataLakeMetadata]:
        stmt = select(DataLakeMetadata).where(
            DataLakeMetadata.catalog_id == catalog_id,
        )
        if metric_name:
            stmt = stmt.where(DataLakeMetadata.metric_name == metric_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Archive ───────────────────────────────────────────────────────────

    async def archive_dataset(
        self, catalog_id: int,
        archive_format: str = "parquet",
        retention_days: int = 365,
        partition_start: date | None = None,
        partition_end: date | None = None,
    ) -> DataLakeArchive:
        from datetime import timedelta

        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Dataset {catalog_id} not found")

        archive_dir = storage._ensure_dir(
            os.path.join(storage.get_lake_dir(), "archives", cat.name),
        )
        archive_name = f"{cat.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{archive_format}"
        archive_path = os.path.join(archive_dir, archive_name)

        rows = storage.load_dataset(cat.layer, cat.name)
        meta = storage.save_dataset(
            "archives", cat.name, rows,
            fmt=archive_format,
            partition_date=partition_start or date.today(),
        )

        record = DataLakeArchive(
            catalog_id=catalog_id,
            archive_path=archive_path,
            archive_format=archive_format,
            row_count=meta["row_count"],
            original_size_bytes=cat.total_size_bytes or meta["file_size"],
            compressed_size_bytes=meta["file_size"],
            partition_start=partition_start,
            partition_end=partition_end,
            retention_until=date.today() + timedelta(days=retention_days),
            checksum=meta["checksum"],
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list_archives(
        self, catalog_id: int | None = None,
    ) -> list[DataLakeArchive]:
        stmt = select(DataLakeArchive).where(
            DataLakeArchive.is_deleted.is_(False),
        )
        if catalog_id:
            stmt = stmt.where(DataLakeArchive.catalog_id == catalog_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Storage ──────────────────────────────────────────────────────────

    async def store_records(
        self, layer: str, dataset_name: str,
        rows: list[dict[str, Any]],
        partition_date: date | None = None,
        version: str | None = None,
        fmt: str = "parquet",
        catalog_id: int | None = None,
    ) -> DataLakeStorageRecord:
        _validate_layer(layer)
        meta = storage.save_dataset(layer, dataset_name, rows, partition_date, version, fmt)
        rec = DataLakeStorageRecord(
            catalog_id=catalog_id,
            layer=layer,
            storage_path=meta["storage_path"],
            file_format=meta["file_format"],
            file_size_bytes=meta["file_size"],
            row_count=meta["row_count"],
            partition_date=partition_date,
            checksum=meta["checksum"],
            ingested_at=datetime.utcnow(),
        )
        self.session.add(rec)
        await self.session.commit()
        await self.session.refresh(rec)
        return rec

    async def load_records(
        self, layer: str, dataset_name: str,
        partition_date: date | None = None,
        version: str | None = None,
    ) -> list[dict[str, Any]]:
        return storage.load_dataset(layer, dataset_name, partition_date, version)

    async def get_storage_stats(self) -> dict[str, Any]:
        return storage.get_storage_stats()

    # ── Data movement between layers ──────────────────────────────────────

    async def move_data(
        self, source_catalog_id: int, target_catalog_id: int,
        pipeline_id: int | None = None,
        transformation: str = "copy",
        partition_date: date | None = None,
    ) -> dict[str, Any]:
        """Move data from one catalog dataset to another (copy-pattern)."""
        src = await self.get_dataset(dataset_id=source_catalog_id)
        dst = await self.get_dataset(dataset_id=target_catalog_id)
        if not src or not dst:
            raise ValueError("Source or target dataset not found")

        rows = storage.load_dataset(src.layer, src.name, partition_date)
        if not rows:
            return {"rows_moved": 0, "status": "no_data"}

        meta = storage.save_dataset(
            dst.layer, dst.name, rows, partition_date,
        )

        src.row_count = len(rows)
        dst.row_count = len(rows)
        dst.total_size_bytes = meta["file_size"]

        if pipeline_id:
            await self.complete_pipeline(
                pipeline_id, rows_read=len(rows), rows_written=len(rows),
            )

        await self.record_lineage(
            source_catalog_id, target_catalog_id,
            transformation=transformation,
            pipeline_id=pipeline_id,
        )

        await self.session.commit()
        return {"rows_moved": len(rows), "status": "ok"}

    # ── Source tracking ────────────────────────────────────────────────

    async def register_source(
        self, catalog_id: int, provider_name: str,
        provider_type: str = "api",
        endpoint_url: str | None = None,
        ingestion_method: str = "full_refresh",
        frequency: str | None = None,
        auth_type: str | None = None,
        source_config_json: str | None = None,
    ) -> DataLakeSource:
        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Dataset {catalog_id} not found")

        existing = await self._find_source(catalog_id, provider_name)
        if existing:
            return existing

        entry = DataLakeSource(
            catalog_id=catalog_id,
            provider_name=provider_name,
            provider_type=provider_type,
            endpoint_url=endpoint_url,
            ingestion_method=ingestion_method,
            frequency=frequency,
            auth_type=auth_type,
            source_config_json=source_config_json,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def get_source(self, source_id: int) -> DataLakeSource | None:
        result = await self.session.execute(
            select(DataLakeSource).where(DataLakeSource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def list_sources(
        self, catalog_id: int | None = None,
    ) -> list[DataLakeSource]:
        stmt = select(DataLakeSource).order_by(
            DataLakeSource.provider_name,
        )
        if catalog_id:
            stmt = stmt.where(DataLakeSource.catalog_id == catalog_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def record_ingestion(
        self, source_id: int,
        catalog_id: int | None = None,
        rows_ingested: int = 0,
        rows_failed: int = 0,
        bytes_fetched: int = 0,
        checksum: str | None = None,
        target_version: str | None = None,
        error_message: str | None = None,
    ) -> DataLakeIngestionRun:
        source = await self.get_source(source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        status = "failed" if error_message else "completed"
        now = datetime.utcnow()

        run = DataLakeIngestionRun(
            source_id=source_id,
            catalog_id=catalog_id or source.catalog_id,
            started_at=None,
            completed_at=now,
            status=status,
            rows_ingested=rows_ingested,
            rows_failed=rows_failed,
            bytes_fetched=bytes_fetched,
            checksum=checksum,
            target_version=target_version,
            error_message=error_message,
        )
        self.session.add(run)

        if status == "completed":
            source.last_success_at = now
            source.retry_count = 0
        else:
            source.last_error_at = now
            source.last_error_message = error_message
            source.retry_count = DataLakeSource.retry_count + 1

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def list_ingestion_runs(
        self, source_id: int | None = None,
        catalog_id: int | None = None,
        limit: int = 50,
    ) -> list[DataLakeIngestionRun]:
        stmt = select(DataLakeIngestionRun).order_by(
            DataLakeIngestionRun.completed_at.desc().nullslast(),
        )
        if source_id:
            stmt = stmt.where(DataLakeIngestionRun.source_id == source_id)
        if catalog_id:
            stmt = stmt.where(DataLakeIngestionRun.catalog_id == catalog_id)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Snapshots / Rollback ────────────────────────────────────────────

    async def create_snapshot(
        self, catalog_id: int, version: str,
        label: str,
        is_restore_point: bool = True,
        metadata_json: str | None = None,
    ) -> DataLakeSnapshot:
        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Dataset {catalog_id} not found")

        ver = await self.get_version(catalog_id, version)
        ver_id = ver.id if ver else None

        rows = storage.load_dataset(cat.layer, cat.name)
        snapshot_dir = storage._ensure_dir(
            os.path.join(storage.get_lake_dir(), "snapshots", cat.name),
        )
        snapshot_path = os.path.join(
            snapshot_dir,
            f"{label.replace(' ', '_')}_{version}.json",
        )
        meta = storage.save_dataset(
            "metadata", f"snapshot_{cat.name}",
            rows, fmt="json",
            partition_date=None, version=label,
        )
        snapshot_path = meta["storage_path"]

        entry = DataLakeSnapshot(
            catalog_id=catalog_id,
            version_id=ver_id,
            version=version,
            label=label,
            snapshot_path=snapshot_path,
            checksum=meta["checksum"],
            row_count=meta["row_count"],
            is_restore_point=is_restore_point,
            metadata_json=metadata_json,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def rollback_to_version(
        self, catalog_id: int, target_version: str,
        label: str | None = None,
    ) -> dict[str, Any]:
        current = await self.get_dataset(dataset_id=catalog_id)
        if not current:
            raise ValueError(f"Dataset {catalog_id} not found")

        ver = await self.get_version(catalog_id, target_version)
        if not ver:
            raise ValueError(f"Version {target_version} not found for dataset {catalog_id}")

        # Create a restore-point snapshot of the current state
        now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        restore_label = label or f"pre_rollback_{now_str}"
        await self.create_snapshot(
            catalog_id, current.schema_version,
            label=restore_label,
            is_restore_point=True,
            metadata_json=json.dumps({
                "reason": f"Rollback to version {target_version}",
                "rolled_back_at": now_str,
            }),
        )

        # Load data from the version's storage path
        rows = storage.load_dataset(
            current.layer, current.name,
            version=target_version,
        )
        if not rows:
            # Try loading from the version's explicit storage path
            rows = storage.load_dataset_by_path(ver.storage_path)
        if not rows and ver.storage_path and os.path.isdir(ver.storage_path):
            rows = storage.load_dataset(current.layer, current.name, version=target_version)

        # Write data back as a new version
        new_ver_str = f"{target_version}.rollback.{now_str}"
        meta = storage.save_dataset(
            current.layer, current.name, rows,
            version=new_ver_str, fmt=current.format,
        )

        # Create the new version record
        new_ver = await self.create_version(
            catalog_id=catalog_id,
            version=new_ver_str,
            storage_path=meta["storage_path"],
            row_count=meta["row_count"],
            checksum=meta["checksum"],
            parent_version=target_version,
            metadata_json=json.dumps({
                "type": "rollback",
                "rolled_back_from": current.schema_version,
                "rolled_back_to": target_version,
                "timestamp": now_str,
            }),
        )

        current.row_count = meta["row_count"]
        current.total_size_bytes = meta["file_size"]
        await self.session.commit()

        return {
            "status": "ok",
            "catalog_id": catalog_id,
            "new_version": new_ver_str,
            "parent_version": target_version,
            "rows_restored": meta["row_count"],
            "restore_point_label": restore_label,
        }

    async def list_snapshots(
        self, catalog_id: int | None = None,
    ) -> list[DataLakeSnapshot]:
        stmt = select(DataLakeSnapshot).order_by(
            DataLakeSnapshot.created_at.desc(),
        )
        if catalog_id:
            stmt = stmt.where(DataLakeSnapshot.catalog_id == catalog_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_snapshot(self, snapshot_id: int) -> DataLakeSnapshot | None:
        result = await self.session.execute(
            select(DataLakeSnapshot).where(DataLakeSnapshot.id == snapshot_id)
        )
        return result.scalar_one_or_none()

    # ── Diff Engine ─────────────────────────────────────────────────────

    async def compute_diff(
        self, catalog_id: int,
        source_version: str, target_version: str,
        key_column: str | None = None,
    ) -> DataLakeDiff:
        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Dataset {catalog_id} not found")

        src_ver = await self.get_version(catalog_id, source_version)
        dst_ver = await self.get_version(catalog_id, target_version)
        if not src_ver or not dst_ver:
            raise ValueError("Source or target version not found")

        src_rows = storage.load_dataset(
            cat.layer, cat.name, version=source_version,
        )
        dst_rows = storage.load_dataset(
            cat.layer, cat.name, version=target_version,
        )

        if not src_rows:
            src_rows = storage.load_dataset_by_path(src_ver.storage_path)
        if not dst_rows:
            dst_rows = storage.load_dataset_by_path(dst_ver.storage_path)

        # Normalise rows to dicts
        src_normalised = [dict(r) for r in src_rows]
        dst_normalised = [dict(r) for r in dst_rows]

        if not src_normalised and not dst_normalised:
            return await self._save_diff(
                catalog_id, src_ver.id, dst_ver.id,
                source_version, target_version,
                0, 0, 0, 0, key_column=key_column,
            )

        # Pick a key column if none given
        all_keys = set()
        for r in src_normalised:
            all_keys.update(r.keys())
        for r in dst_normalised:
            all_keys.update(r.keys())

        if not key_column:
            candidates = [c for c in ("id", "symbol", "name", "date", "key") if c in all_keys]
            key_column = candidates[0] if candidates else None

        if not key_column:
            raise ValueError(
                "Cannot determine key column. Specify a key_column or ensure "
                "one of 'id', 'symbol', 'name', 'date', 'key' exists."
            )

        # Build lookup maps
        src_map: dict[str, dict] = {}
        for r in src_normalised:
            k = str(r.get(key_column, ""))
            src_map[k] = r

        dst_map: dict[str, dict] = {}
        for r in dst_normalised:
            k = str(r.get(key_column, ""))
            dst_map[k] = r

        src_keys = set(src_map.keys())
        dst_keys = set(dst_map.keys())

        added_keys = dst_keys - src_keys
        removed_keys = src_keys - dst_keys
        common_keys = src_keys & dst_keys

        modified = 0
        unchanged = 0
        diff_details: list[dict] = []

        for k in sorted(common_keys):
            if src_map[k] != dst_map[k]:
                modified += 1
                if len(diff_details) < 100:  # cap detail
                    diff_details.append({
                        "key": k,
                        "old": src_map[k],
                        "new": dst_map[k],
                    })
            else:
                unchanged += 1

        added = len(added_keys)
        removed = len(removed_keys)

        summary = {
            "key_column": key_column,
            "sample_changes": diff_details,
            "added_keys": sorted(added_keys)[:50],
            "removed_keys": sorted(removed_keys)[:50],
        }

        return await self._save_diff(
            catalog_id, src_ver.id, dst_ver.id,
            source_version, target_version,
            added, removed, modified, unchanged,
            key_column=key_column,
            diff_summary=json.dumps(summary),
        )

    async def get_diff(
        self, diff_id: int,
    ) -> DataLakeDiff | None:
        result = await self.session.execute(
            select(DataLakeDiff).where(DataLakeDiff.id == diff_id)
        )
        return result.scalar_one_or_none()

    async def list_diffs(
        self, catalog_id: int | None = None,
        limit: int = 50,
    ) -> list[DataLakeDiff]:
        stmt = select(DataLakeDiff).order_by(
            DataLakeDiff.created_at.desc(),
        )
        if catalog_id:
            stmt = stmt.where(DataLakeDiff.catalog_id == catalog_id)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _save_diff(
        self, catalog_id: int,
        source_version_id: int, target_version_id: int,
        source_version: str, target_version: str,
        added: int, removed: int, modified: int, unchanged: int,
        key_column: str | None = None,
        diff_summary: str | None = None,
    ) -> DataLakeDiff:
        entry = DataLakeDiff(
            catalog_id=catalog_id,
            source_version_id=source_version_id,
            target_version_id=target_version_id,
            source_version=source_version,
            target_version=target_version,
            added_count=added,
            removed_count=removed,
            modified_count=modified,
            unchanged_count=unchanged,
            diff_summary=diff_summary,
            key_column=key_column,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    # ── Checksum management ─────────────────────────────────────────────

    async def verify_checksum(self, catalog_id: int, version: str) -> dict[str, Any]:
        ver = await self.get_version(catalog_id, version)
        if not ver:
            raise ValueError(f"Version {version} not found for catalog {catalog_id}")

        cat = await self.get_dataset(dataset_id=catalog_id)
        if not cat:
            raise ValueError(f"Catalog {catalog_id} not found")

        rows = storage.load_dataset(cat.layer, cat.name, version=version)
        import hashlib, json as _json

        content = _json.dumps(rows, default=str).encode("utf-8")
        actual = hashlib.sha256(content).hexdigest()[:32]
        stored = ver.checksum or ""

        return {
            "catalog_id": catalog_id,
            "version": version,
            "stored_checksum": stored,
            "actual_checksum": actual,
            "match": actual == stored,
            "row_count": len(rows),
        }

    # ── Internals ────────────────────────────────────────────────────────

    async def _find_catalog(
        self, name: str, layer: str,
    ) -> DataLakeCatalog | None:
        result = await self.session.execute(
            select(DataLakeCatalog).where(
                DataLakeCatalog.name == name,
                DataLakeCatalog.layer == layer,
            )
        )
        return result.scalar_one_or_none()

    async def _get_pipeline(
        self, pipeline_id: int,
    ) -> DataLakePipeline | None:
        result = await self.session.execute(
            select(DataLakePipeline).where(DataLakePipeline.id == pipeline_id)
        )
        return result.scalar_one_or_none()

    async def _find_source(
        self, catalog_id: int, provider_name: str,
    ) -> DataLakeSource | None:
        result = await self.session.execute(
            select(DataLakeSource).where(
                DataLakeSource.catalog_id == catalog_id,
                DataLakeSource.provider_name == provider_name,
            )
        )
        return result.scalar_one_or_none()



