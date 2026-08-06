"""Data Lake API endpoints.

Full CRUD for datasets, schemas, versions, pipelines, lineage, archival,
metadata, and data movement across the 8 layers.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.data_lake import DATALAKE_LAYERS
from titan_x.services.datalake_service import DataLakeService

from . import schemas
from .serializers import (
    archive_to_dict,
    catalog_to_dict,
    diff_to_dict,
    ingestion_to_dict,
    lineage_to_dict,
    metadata_to_dict,
    pipeline_to_dict,
    schema_to_dict,
    snapshot_to_dict,
    source_to_dict,
    version_to_dict,
)


def _serialize_storage_record(rec: Any) -> dict[str, Any]:
    return {
        "id": rec.id,
        "storage_path": rec.storage_path,
        "file_format": rec.file_format,
        "file_size_bytes": rec.file_size_bytes,
        "row_count": rec.row_count,
        "checksum": rec.checksum,
    }


router = APIRouter(prefix="/datalake", tags=["datalake"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> DataLakeService:
    return DataLakeService(session)


@router.get("/layers")
async def list_layers() -> list[str]:
    return list(DATALAKE_LAYERS)


# ── Datasets (Catalog) ───────────────────────────────────────────────────────


@router.post("/datasets", status_code=201)
async def create_dataset(
    body: schemas.DatasetCreate,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    ds = await service.register_dataset(
        name=body.name,
        layer=body.layer,
        storage_path=body.storage_path,
        format=body.format,
        description=body.description,
        tags=body.tags,
        partition_columns=body.partition_columns,
        source=body.source,
    )
    return catalog_to_dict(ds)


@router.get("/datasets")
async def list_datasets(
    layer: str | None = Query(None),
    active_only: bool = Query(True),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    datasets = await service.list_datasets(layer=layer, active_only=active_only)
    return [catalog_to_dict(d) for d in datasets]


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    ds = await service.get_dataset(dataset_id=dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return catalog_to_dict(ds)


@router.patch("/datasets/{dataset_id}")
async def update_dataset(
    dataset_id: int,
    body: schemas.DatasetUpdate,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    kwargs = body.model_dump(exclude_none=True)
    ds = await service.update_dataset(dataset_id, **kwargs)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return catalog_to_dict(ds)


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    remove_files: bool = Query(False),
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    ok = await service.delete_dataset(dataset_id, remove_files=remove_files)
    if not ok:
        raise HTTPException(404, "Dataset not found")
    return {"status": "deleted"}


# ── Schemas ──────────────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/schemas", status_code=201)
async def register_schema(
    catalog_id: int,
    body: schemas.SchemaRegister,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        s = await service.register_schema(
            catalog_id, body.schema_def, body.version, body.created_by,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return schema_to_dict(s)


@router.get("/datasets/{catalog_id}/schemas")
async def list_schemas(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    schemas_rows = await service.list_schemas(catalog_id)
    return [schema_to_dict(s) for s in schemas_rows]


@router.get("/datasets/{catalog_id}/schemas/active")
async def get_active_schema(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    s = await service.get_schema(catalog_id)
    if not s:
        raise HTTPException(404, "No active schema found")
    return schema_to_dict(s)


# ── Versions ─────────────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/versions", status_code=201)
async def create_version(
    catalog_id: int,
    body: schemas.VersionCreate,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    v = await service.create_version(
        catalog_id=catalog_id,
        version=body.version,
        storage_path=body.storage_path,
        row_count=body.row_count,
        checksum=body.checksum,
        metadata_json=body.metadata_json,
        parent_version=body.parent_version,
    )
    return version_to_dict(v)


@router.get("/datasets/{catalog_id}/versions")
async def list_versions(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    versions = await service.list_versions(catalog_id)
    return [version_to_dict(v) for v in versions]


# ── Pipelines ────────────────────────────────────────────────────────────────


@router.post("/pipelines", status_code=201)
async def create_pipeline(
    body: schemas.PipelineCreate,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        p = await service.create_pipeline(
            name=body.name,
            source_layer=body.source_layer,
            target_layer=body.target_layer,
            source_catalog_id=body.source_catalog_id,
            target_catalog_id=body.target_catalog_id,
            pipeline_type=body.pipeline_type,
            config_json=body.config_json,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return pipeline_to_dict(p)


@router.post("/pipelines/{pipeline_id}/start")
async def start_pipeline(
    pipeline_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    p = await service.start_pipeline(pipeline_id)
    if not p:
        raise HTTPException(404, "Pipeline not found")
    return pipeline_to_dict(p)


@router.post("/pipelines/{pipeline_id}/complete")
async def complete_pipeline(
    pipeline_id: int,
    body: schemas.PipelineComplete,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    p = await service.complete_pipeline(
        pipeline_id,
        rows_read=body.rows_read,
        rows_written=body.rows_written,
        rows_failed=body.rows_failed,
        error_message=body.error_message,
    )
    if not p:
        raise HTTPException(404, "Pipeline not found")
    return pipeline_to_dict(p)


@router.get("/pipelines")
async def list_pipelines(
    status: str | None = Query(None),
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    pipelines = await service.list_pipelines(status=status, limit=limit)
    return [pipeline_to_dict(p) for p in pipelines]


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(
    pipeline_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    p = await service.get_pipeline(pipeline_id)
    if not p:
        raise HTTPException(404, "Pipeline not found")
    return pipeline_to_dict(p)


# ── Lineage ──────────────────────────────────────────────────────────────────


@router.post("/lineage", status_code=201)
async def record_lineage(
    body: schemas.LineageRecord,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        ln = await service.record_lineage(
            source_catalog_id=body.source_catalog_id,
            target_catalog_id=body.target_catalog_id,
            transformation=body.transformation,
            pipeline_id=body.pipeline_id,
            source_version=body.source_version,
            target_version=body.target_version,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return lineage_to_dict(ln)


@router.get("/lineage/downstream/{catalog_id}")
async def get_downstream(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [lineage_to_dict(ln) for ln in await service.get_downstream(catalog_id)]


@router.get("/lineage/upstream/{catalog_id}")
async def get_upstream(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [lineage_to_dict(ln) for ln in await service.get_upstream(catalog_id)]


@router.get("/lineage/graph/{catalog_id}")
async def get_lineage_graph(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.get_lineage_graph(catalog_id)


# ── Metadata ─────────────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/metadata", status_code=201)
async def set_metadata(
    catalog_id: int,
    body: schemas.MetadataSet,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    m = await service.set_metadata(
        catalog_id, body.metric_name, body.metric_value, body.metric_type,
    )
    return metadata_to_dict(m)


@router.get("/datasets/{catalog_id}/metadata")
async def get_metadata(
    catalog_id: int,
    metric_name: str | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        metadata_to_dict(m)
        for m in await service.get_metadata(catalog_id, metric_name)
    ]


# ── Archives ─────────────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/archive", status_code=201)
async def archive_dataset(
    catalog_id: int,
    body: schemas.ArchiveCreate,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        a = await service.archive_dataset(
            catalog_id=catalog_id,
            archive_format=body.archive_format,
            retention_days=body.retention_days,
            partition_start=body.partition_start,
            partition_end=body.partition_end,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return archive_to_dict(a)


@router.get("/archives")
async def list_archives(
    catalog_id: int | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        archive_to_dict(a) for a in await service.list_archives(catalog_id)
    ]


# ── Storage / Data Movement ──────────────────────────────────────────────────


@router.post("/storage/records", status_code=201)
async def store_records(
    body: schemas.StoreRecords,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    rec = await service.store_records(
        layer=body.layer,
        dataset_name=body.dataset_name,
        rows=body.rows,
        partition_date=body.partition_date,
        version=body.version,
        fmt=body.format,
        catalog_id=body.catalog_id,
    )
    return _serialize_storage_record(rec)


@router.get("/storage/load")
async def load_records(
    layer: str = Query(...),
    dataset_name: str = Query(...),
    partition_date: date | None = Query(None),
    version: str | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return await service.load_records(layer, dataset_name, partition_date, version)


@router.post("/move")
async def move_data(
    source_catalog_id: int = Query(...),
    target_catalog_id: int = Query(...),
    pipeline_id: int | None = Query(None),
    body: schemas.DataMove = schemas.DataMove(),
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        return await service.move_data(
            source_catalog_id, target_catalog_id,
            pipeline_id=pipeline_id,
            transformation=body.transformation,
            partition_date=body.partition_date,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/storage/stats")
async def storage_stats(
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.get_storage_stats()


# ── Source tracking ──────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/sources", status_code=201)
async def register_source(
    catalog_id: int,
    body: schemas.SourceRegister,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        src = await service.register_source(
            catalog_id=catalog_id,
            provider_name=body.provider_name,
            provider_type=body.provider_type,
            endpoint_url=body.endpoint_url,
            ingestion_method=body.ingestion_method,
            frequency=body.frequency,
            auth_type=body.auth_type,
            source_config_json=body.source_config_json,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return source_to_dict(src)


@router.get("/sources")
async def list_sources(
    catalog_id: int | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [source_to_dict(s) for s in await service.list_sources(catalog_id)]


@router.get("/sources/{source_id}")
async def get_source(
    source_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    src = await service.get_source(source_id)
    if not src:
        raise HTTPException(404, "Source not found")
    return source_to_dict(src)


@router.post("/sources/{source_id}/ingest", status_code=201)
async def record_ingestion(
    source_id: int,
    body: schemas.IngestionRecord,
    catalog_id: int | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        run = await service.record_ingestion(
            source_id=source_id,
            catalog_id=catalog_id,
            rows_ingested=body.rows_ingested,
            rows_failed=body.rows_failed,
            bytes_fetched=body.bytes_fetched,
            checksum=body.checksum,
            target_version=body.target_version,
            error_message=body.error_message,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return ingestion_to_dict(run)


@router.get("/sources/{source_id}/ingestions")
async def list_ingestion_runs(
    source_id: int,
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        ingestion_to_dict(r)
        for r in await service.list_ingestion_runs(source_id=source_id, limit=limit)
    ]


@router.get("/ingestions")
async def list_all_ingestions(
    catalog_id: int | None = Query(None),
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        ingestion_to_dict(r)
        for r in await service.list_ingestion_runs(catalog_id=catalog_id, limit=limit)
    ]


# ── Snapshots / Rollback ─────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/snapshots", status_code=201)
async def create_snapshot(
    catalog_id: int,
    body: schemas.SnapshotCreate,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        snap = await service.create_snapshot(
            catalog_id=catalog_id,
            version=body.version,
            label=body.label,
            is_restore_point=body.is_restore_point,
            metadata_json=body.metadata_json,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return snapshot_to_dict(snap)


@router.get("/snapshots")
async def list_snapshots(
    catalog_id: int | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [snapshot_to_dict(s) for s in await service.list_snapshots(catalog_id)]


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    snap = await service.get_snapshot(snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    return snapshot_to_dict(snap)


@router.post("/datasets/{catalog_id}/rollback")
async def rollback_dataset(
    catalog_id: int,
    body: schemas.RollbackRequest,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        return await service.rollback_to_version(
            catalog_id=catalog_id,
            target_version=body.target_version,
            label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ── Diff Engine ──────────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/diffs", status_code=201)
async def compute_diff(
    catalog_id: int,
    body: schemas.DiffRequest,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        diff = await service.compute_diff(
            catalog_id=catalog_id,
            source_version=body.source_version,
            target_version=body.target_version,
            key_column=body.key_column,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return diff_to_dict(diff)


@router.get("/diffs")
async def list_diffs(
    catalog_id: int | None = Query(None),
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [diff_to_dict(d) for d in await service.list_diffs(catalog_id, limit)]


@router.get("/diffs/{diff_id}")
async def get_diff(
    diff_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    diff = await service.get_diff(diff_id)
    if not diff:
        raise HTTPException(404, "Diff not found")
    return diff_to_dict(diff)


# ── Checksum ─────────────────────────────────────────────────────────────────


@router.get("/datasets/{catalog_id}/versions/{version}/checksum")
async def verify_checksum(
    catalog_id: int,
    version: str,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        return await service.verify_checksum(catalog_id, version)
    except ValueError as exc:
        raise HTTPException(400, str(exc))