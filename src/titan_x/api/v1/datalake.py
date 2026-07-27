"""Data Lake API endpoints.

Full CRUD for datasets, schemas, versions, pipelines, lineage, archival,
metadata, and data movement across the 8 layers.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.models.data_lake import DATALAKE_LAYERS
from titan_x.services.datalake_service import DataLakeService

router = APIRouter(prefix="/datalake", tags=["datalake"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    layer: str = Field(..., pattern=f"^({'|'.join(DATALAKE_LAYERS)})$")
    storage_path: str | None = None
    format: str = "parquet"
    description: str | None = None
    tags: str | None = None
    partition_columns: str | None = None
    source: str | None = None


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: str | None = None
    is_active: bool | None = None


class SchemaRegister(BaseModel):
    schema_def: dict[str, Any]
    version: str = "1.0.0"
    created_by: str | None = None


class VersionCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=16)
    storage_path: str
    row_count: int = 0
    checksum: str | None = None
    metadata_json: str | None = None
    parent_version: str | None = None


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    source_layer: str
    target_layer: str
    source_catalog_id: int | None = None
    target_catalog_id: int | None = None
    pipeline_type: str = "transform"
    config_json: str | None = None


class PipelineComplete(BaseModel):
    rows_read: int = 0
    rows_written: int = 0
    rows_failed: int = 0
    error_message: str | None = None


class LineageRecord(BaseModel):
    source_catalog_id: int
    target_catalog_id: int
    transformation: str
    pipeline_id: int | None = None
    source_version: str | None = None
    target_version: str | None = None


class MetadataSet(BaseModel):
    metric_name: str
    metric_value: str
    metric_type: str = "string"


class DataMove(BaseModel):
    transformation: str = "copy"
    partition_date: date | None = None


class ArchiveCreate(BaseModel):
    archive_format: str = "parquet"
    retention_days: int = 365
    partition_start: date | None = None
    partition_end: date | None = None


class StoreRecords(BaseModel):
    layer: str
    dataset_name: str
    rows: list[dict[str, Any]]
    partition_date: date | None = None
    version: str | None = None
    format: str = "parquet"
    catalog_id: int | None = None


class SourceRegister(BaseModel):
    provider_name: str = Field(..., min_length=1, max_length=128)
    provider_type: str = "api"
    endpoint_url: str | None = None
    ingestion_method: str = "full_refresh"
    frequency: str | None = None
    auth_type: str | None = None
    source_config_json: str | None = None


class IngestionRecord(BaseModel):
    rows_ingested: int = 0
    rows_failed: int = 0
    bytes_fetched: int = 0
    checksum: str | None = None
    target_version: str | None = None
    error_message: str | None = None


class SnapshotCreate(BaseModel):
    version: str
    label: str = Field(..., min_length=1, max_length=128)
    is_restore_point: bool = True
    metadata_json: str | None = None


class RollbackRequest(BaseModel):
    target_version: str
    label: str | None = None


class DiffRequest(BaseModel):
    source_version: str
    target_version: str
    key_column: str | None = None


class ChecksumVerify(BaseModel):
    version: str


# ── Dependency ───────────────────────────────────────────────────────────────


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> DataLakeService:
    return DataLakeService(session)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/layers")
async def list_layers() -> list[str]:
    return list(DATALAKE_LAYERS)


# ── Datasets (Catalog) ───────────────────────────────────────────────────────


@router.post("/datasets", status_code=201)
async def create_dataset(
    body: DatasetCreate,
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
    return _catalog_to_dict(ds)


@router.get("/datasets")
async def list_datasets(
    layer: str | None = Query(None),
    active_only: bool = Query(True),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    datasets = await service.list_datasets(layer=layer, active_only=active_only)
    return [_catalog_to_dict(d) for d in datasets]


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    ds = await service.get_dataset(dataset_id=dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return _catalog_to_dict(ds)


@router.patch("/datasets/{dataset_id}")
async def update_dataset(
    dataset_id: int,
    body: DatasetUpdate,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    kwargs = body.model_dump(exclude_none=True)
    ds = await service.update_dataset(dataset_id, **kwargs)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return _catalog_to_dict(ds)


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
    body: SchemaRegister,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    try:
        s = await service.register_schema(
            catalog_id, body.schema_def, body.version, body.created_by,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return _schema_to_dict(s)


@router.get("/datasets/{catalog_id}/schemas")
async def list_schemas(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    schemas = await service.list_schemas(catalog_id)
    return [_schema_to_dict(s) for s in schemas]


@router.get("/datasets/{catalog_id}/schemas/active")
async def get_active_schema(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    s = await service.get_schema(catalog_id)
    if not s:
        raise HTTPException(404, "No active schema found")
    return _schema_to_dict(s)


# ── Versions ─────────────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/versions", status_code=201)
async def create_version(
    catalog_id: int,
    body: VersionCreate,
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
    return _version_to_dict(v)


@router.get("/datasets/{catalog_id}/versions")
async def list_versions(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    versions = await service.list_versions(catalog_id)
    return [_version_to_dict(v) for v in versions]


# ── Pipelines ────────────────────────────────────────────────────────────────


@router.post("/pipelines", status_code=201)
async def create_pipeline(
    body: PipelineCreate,
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
    return _pipeline_to_dict(p)


@router.post("/pipelines/{pipeline_id}/start")
async def start_pipeline(
    pipeline_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    p = await service.start_pipeline(pipeline_id)
    if not p:
        raise HTTPException(404, "Pipeline not found")
    return _pipeline_to_dict(p)


@router.post("/pipelines/{pipeline_id}/complete")
async def complete_pipeline(
    pipeline_id: int,
    body: PipelineComplete,
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
    return _pipeline_to_dict(p)


@router.get("/pipelines")
async def list_pipelines(
    status: str | None = Query(None),
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    pipelines = await service.list_pipelines(status=status, limit=limit)
    return [_pipeline_to_dict(p) for p in pipelines]


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(
    pipeline_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    p = await service.get_pipeline(pipeline_id)
    if not p:
        raise HTTPException(404, "Pipeline not found")
    return _pipeline_to_dict(p)


# ── Lineage ──────────────────────────────────────────────────────────────────


@router.post("/lineage", status_code=201)
async def record_lineage(
    body: LineageRecord,
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
    return _lineage_to_dict(ln)


@router.get("/lineage/downstream/{catalog_id}")
async def get_downstream(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [_lineage_to_dict(ln) for ln in await service.get_downstream(catalog_id)]


@router.get("/lineage/upstream/{catalog_id}")
async def get_upstream(
    catalog_id: int,
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [_lineage_to_dict(ln) for ln in await service.get_upstream(catalog_id)]


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
    body: MetadataSet,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    m = await service.set_metadata(
        catalog_id, body.metric_name, body.metric_value, body.metric_type,
    )
    return _metadata_to_dict(m)


@router.get("/datasets/{catalog_id}/metadata")
async def get_metadata(
    catalog_id: int,
    metric_name: str | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        _metadata_to_dict(m)
        for m in await service.get_metadata(catalog_id, metric_name)
    ]


# ── Archives ─────────────────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/archive", status_code=201)
async def archive_dataset(
    catalog_id: int,
    body: ArchiveCreate,
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
    return _archive_to_dict(a)


@router.get("/archives")
async def list_archives(
    catalog_id: int | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        _archive_to_dict(a) for a in await service.list_archives(catalog_id)
    ]


# ── Storage / Data Movement ──────────────────────────────────────────────────


@router.post("/storage/records", status_code=201)
async def store_records(
    body: StoreRecords,
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
    return {
        "id": rec.id,
        "storage_path": rec.storage_path,
        "file_format": rec.file_format,
        "file_size_bytes": rec.file_size_bytes,
        "row_count": rec.row_count,
        "checksum": rec.checksum,
    }


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
    body: DataMove = DataMove(),
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
    body: SourceRegister,
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
    return _source_to_dict(src)


@router.get("/sources")
async def list_sources(
    catalog_id: int | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [_source_to_dict(s) for s in await service.list_sources(catalog_id)]


@router.get("/sources/{source_id}")
async def get_source(
    source_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    src = await service.get_source(source_id)
    if not src:
        raise HTTPException(404, "Source not found")
    return _source_to_dict(src)


@router.post("/sources/{source_id}/ingest", status_code=201)
async def record_ingestion(
    source_id: int,
    body: IngestionRecord,
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
    return _ingestion_to_dict(run)


@router.get("/sources/{source_id}/ingestions")
async def list_ingestion_runs(
    source_id: int,
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        _ingestion_to_dict(r)
        for r in await service.list_ingestion_runs(source_id=source_id, limit=limit)
    ]


@router.get("/ingestions")
async def list_all_ingestions(
    catalog_id: int | None = Query(None),
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [
        _ingestion_to_dict(r)
        for r in await service.list_ingestion_runs(catalog_id=catalog_id, limit=limit)
    ]


# ── Snapshots / Rollback ─────────────────────────────────────────────────────


@router.post("/datasets/{catalog_id}/snapshots", status_code=201)
async def create_snapshot(
    catalog_id: int,
    body: SnapshotCreate,
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
    return _snapshot_to_dict(snap)


@router.get("/snapshots")
async def list_snapshots(
    catalog_id: int | None = Query(None),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [_snapshot_to_dict(s) for s in await service.list_snapshots(catalog_id)]


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    snap = await service.get_snapshot(snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    return _snapshot_to_dict(snap)


@router.post("/datasets/{catalog_id}/rollback")
async def rollback_dataset(
    catalog_id: int,
    body: RollbackRequest,
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
    body: DiffRequest,
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
    return _diff_to_dict(diff)


@router.get("/diffs")
async def list_diffs(
    catalog_id: int | None = Query(None),
    limit: int = Query(50),
    service: DataLakeService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return [_diff_to_dict(d) for d in await service.list_diffs(catalog_id, limit)]


@router.get("/diffs/{diff_id}")
async def get_diff(
    diff_id: int,
    service: DataLakeService = Depends(_get_service),
) -> dict[str, Any]:
    diff = await service.get_diff(diff_id)
    if not diff:
        raise HTTPException(404, "Diff not found")
    return _diff_to_dict(diff)


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


# ── Serializers ──────────────────────────────────────────────────────────────


def _catalog_to_dict(ds: Any) -> dict[str, Any]:
    return {
        "id": ds.id,
        "name": ds.name,
        "layer": ds.layer,
        "storage_path": ds.storage_path,
        "format": ds.format,
        "schema_version": ds.schema_version,
        "row_count": ds.row_count,
        "file_count": ds.file_count,
        "total_size_bytes": ds.total_size_bytes,
        "is_active": ds.is_active,
        "description": ds.description,
        "tags": ds.tags,
        "partition_columns": ds.partition_columns,
        "source": ds.source,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
    }


def _schema_to_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "catalog_id": s.catalog_id,
        "version": s.version,
        "schema_definition": s.schema_definition,
        "columns": s.columns,
        "created_by": s.created_by,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _version_to_dict(v: Any) -> dict[str, Any]:
    return {
        "id": v.id,
        "catalog_id": v.catalog_id,
        "version": v.version,
        "parent_version": v.parent_version,
        "storage_path": v.storage_path,
        "row_count": v.row_count,
        "checksum": v.checksum,
        "metadata_json": v.metadata_json,
        "is_archived": v.is_archived,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _pipeline_to_dict(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "source_layer": p.source_layer,
        "target_layer": p.target_layer,
        "source_catalog_id": p.source_catalog_id,
        "target_catalog_id": p.target_catalog_id,
        "status": p.status,
        "started_at": p.started_at.isoformat() if p.started_at else None,
        "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        "rows_read": p.rows_read,
        "rows_written": p.rows_written,
        "rows_failed": p.rows_failed,
        "error_message": p.error_message,
        "pipeline_type": p.pipeline_type,
        "config_json": p.config_json,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _lineage_to_dict(ln: Any) -> dict[str, Any]:
    return {
        "id": ln.id,
        "source_catalog_id": ln.source_catalog_id,
        "target_catalog_id": ln.target_catalog_id,
        "pipeline_id": ln.pipeline_id,
        "transformation": ln.transformation,
        "source_version": ln.source_version,
        "target_version": ln.target_version,
        "created_at": ln.created_at.isoformat() if ln.created_at else None,
    }


def _metadata_to_dict(m: Any) -> dict[str, Any]:
    return {
        "id": m.id,
        "catalog_id": m.catalog_id,
        "metric_name": m.metric_name,
        "metric_value": m.metric_value,
        "metric_type": m.metric_type,
        "computed_at": m.computed_at.isoformat() if m.computed_at else None,
    }


def _archive_to_dict(a: Any) -> dict[str, Any]:
    return {
        "id": a.id,
        "catalog_id": a.catalog_id,
        "archive_path": a.archive_path,
        "archive_format": a.archive_format,
        "row_count": a.row_count,
        "original_size_bytes": a.original_size_bytes,
        "compressed_size_bytes": a.compressed_size_bytes,
        "partition_start": a.partition_start.isoformat() if a.partition_start else None,
        "partition_end": a.partition_end.isoformat() if a.partition_end else None,
        "retention_until": a.retention_until.isoformat() if a.retention_until else None,
        "is_deleted": a.is_deleted,
        "checksum": a.checksum,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _source_to_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "catalog_id": s.catalog_id,
        "provider_name": s.provider_name,
        "provider_type": s.provider_type,
        "endpoint_url": s.endpoint_url,
        "ingestion_method": s.ingestion_method,
        "frequency": s.frequency,
        "auth_type": s.auth_type,
        "retry_count": s.retry_count,
        "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
        "last_error_at": s.last_error_at.isoformat() if s.last_error_at else None,
        "last_error_message": s.last_error_message,
        "is_active": s.is_active,
        "source_config_json": s.source_config_json,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _ingestion_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "source_id": r.source_id,
        "catalog_id": r.catalog_id,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "status": r.status,
        "rows_ingested": r.rows_ingested,
        "rows_failed": r.rows_failed,
        "bytes_fetched": r.bytes_fetched,
        "error_message": r.error_message,
        "checksum": r.checksum,
        "target_version": r.target_version,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _snapshot_to_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "catalog_id": s.catalog_id,
        "version_id": s.version_id,
        "version": s.version,
        "label": s.label,
        "snapshot_path": s.snapshot_path,
        "checksum": s.checksum,
        "row_count": s.row_count,
        "is_restore_point": s.is_restore_point,
        "metadata_json": s.metadata_json,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _diff_to_dict(d: Any) -> dict[str, Any]:
    return {
        "id": d.id,
        "catalog_id": d.catalog_id,
        "source_version_id": d.source_version_id,
        "target_version_id": d.target_version_id,
        "source_version": d.source_version,
        "target_version": d.target_version,
        "added_count": d.added_count,
        "removed_count": d.removed_count,
        "modified_count": d.modified_count,
        "unchanged_count": d.unchanged_count,
        "diff_summary": d.diff_summary,
        "key_column": d.key_column,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
