"""Pydantic request schemas for the Data Lake API."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from titan_x.models.data_lake import DATALAKE_LAYERS


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