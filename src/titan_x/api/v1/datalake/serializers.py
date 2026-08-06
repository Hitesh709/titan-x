"""Response serializers for the Data Lake API."""
from __future__ import annotations

from typing import Any


def catalog_to_dict(ds: Any) -> dict[str, Any]:
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


def schema_to_dict(s: Any) -> dict[str, Any]:
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


def version_to_dict(v: Any) -> dict[str, Any]:
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


def pipeline_to_dict(p: Any) -> dict[str, Any]:
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


def lineage_to_dict(ln: Any) -> dict[str, Any]:
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


def metadata_to_dict(m: Any) -> dict[str, Any]:
    return {
        "id": m.id,
        "catalog_id": m.catalog_id,
        "metric_name": m.metric_name,
        "metric_value": m.metric_value,
        "metric_type": m.metric_type,
        "computed_at": m.computed_at.isoformat() if m.computed_at else None,
    }


def archive_to_dict(a: Any) -> dict[str, Any]:
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


def source_to_dict(s: Any) -> dict[str, Any]:
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


def ingestion_to_dict(r: Any) -> dict[str, Any]:
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


def snapshot_to_dict(s: Any) -> dict[str, Any]:
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


def diff_to_dict(d: Any) -> dict[str, Any]:
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