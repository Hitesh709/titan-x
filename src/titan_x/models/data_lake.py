from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


DATALAKE_LAYERS = (
    "raw", "validated", "normalized", "features",
    "predictions", "archives", "metadata", "staging",
)


class DataLakeCatalog(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_catalog"
    __table_args__ = (
        UniqueConstraint("name", "layer", name="uq_dl_cat_name_layer"),
        Index("ix_dl_catalog_layer", "layer"),
        Index("ix_dl_catalog_is_active", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(16), default="parquet", nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0.0", nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    partition_columns: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)

    schemas: Mapped[list["DataLakeSchema"]] = relationship(
        back_populates="catalog", cascade="all, delete-orphan",
    )
    versions: Mapped[list["DataLakeVersion"]] = relationship(
        back_populates="catalog", cascade="all, delete-orphan",
    )
    archives: Mapped[list["DataLakeArchive"]] = relationship(
        back_populates="catalog", cascade="all, delete-orphan",
    )
    lineage_as_source: Mapped[list["DataLakeLineage"]] = relationship(
        back_populates="source_dataset",
        foreign_keys="DataLakeLineage.source_catalog_id",
        cascade="all, delete-orphan",
    )
    lineage_as_target: Mapped[list["DataLakeLineage"]] = relationship(
        back_populates="target_dataset",
        foreign_keys="DataLakeLineage.target_catalog_id",
        cascade="all, delete-orphan",
    )


class DataLakeSchema(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_schemas"
    __table_args__ = (
        UniqueConstraint("catalog_id", "version", name="uq_dl_schema_cat_ver"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_definition: Mapped[str] = mapped_column(Text, nullable=False)
    columns: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    catalog: Mapped["DataLakeCatalog"] = relationship(back_populates="schemas")


class DataLakeVersion(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_versions"
    __table_args__ = (
        UniqueConstraint("catalog_id", "version", name="uq_dl_ver_cat_ver"),
        Index("ix_dl_version_catalog", "catalog_id"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    catalog: Mapped["DataLakeCatalog"] = relationship(back_populates="versions")


class DataLakePipeline(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_pipelines"
    __table_args__ = (
        Index("ix_dl_pipeline_name", "name"),
        Index("ix_dl_pipeline_status", "status"),
        Index("ix_dl_pipeline_started", "started_at"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_layer: Mapped[str] = mapped_column(String(32), nullable=False)
    target_layer: Mapped[str] = mapped_column(String(32), nullable=False)
    source_catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="SET NULL"), nullable=True,
    )
    target_catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="SET NULL"), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_type: Mapped[str] = mapped_column(
        String(32), default="transform", nullable=False,
    )
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    lineage_entries: Mapped[list["DataLakeLineage"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan",
    )


class DataLakeLineage(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_lineage"
    __table_args__ = (
        Index("ix_dl_lineage_source", "source_catalog_id"),
        Index("ix_dl_lineage_target", "target_catalog_id"),
        Index("ix_dl_lineage_pipeline", "pipeline_id"),
    )

    source_catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    target_catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    pipeline_id: Mapped[int | None] = mapped_column(
        ForeignKey("datalake_pipelines.id", ondelete="SET NULL"), nullable=True,
    )
    transformation: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    source_dataset: Mapped["DataLakeCatalog"] = relationship(
        back_populates="lineage_as_source",
        foreign_keys=[source_catalog_id],
    )
    target_dataset: Mapped["DataLakeCatalog"] = relationship(
        back_populates="lineage_as_target",
        foreign_keys=[target_catalog_id],
    )
    pipeline: Mapped["DataLakePipeline | None"] = relationship(
        back_populates="lineage_entries",
    )


class DataLakeArchive(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_archives"
    __table_args__ = (
        Index("ix_dl_archive_catalog", "catalog_id"),
        Index("ix_dl_archive_retention", "retention_until"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    archive_path: Mapped[str] = mapped_column(String(512), nullable=False)
    archive_format: Mapped[str] = mapped_column(String(16), default="parquet", nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    original_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compressed_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    partition_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    partition_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    retention_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)

    catalog: Mapped["DataLakeCatalog"] = relationship(back_populates="archives")


class DataLakeMetadata(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_dataset_metadata"
    __table_args__ = (
        UniqueConstraint("catalog_id", "metric_name", name="uq_dl_meta_cat_metric"),
        Index("ix_dl_meta_catalog", "catalog_id"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_value: Mapped[str] = mapped_column(Text, nullable=False)
    metric_type: Mapped[str] = mapped_column(
        String(16), default="string", nullable=False,
    )
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    catalog: Mapped["DataLakeCatalog"] = relationship()


class DataLakeStorageRecord(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_storage_records"
    __table_args__ = (
        Index("ix_dl_storage_path", "storage_path"),
        Index("ix_dl_storage_layer", "layer"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="SET NULL"), nullable=True,
    )
    layer: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    compression_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DataLakeSource(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_sources"
    __table_args__ = (
        UniqueConstraint("catalog_id", "provider_name", name="uq_dl_src_cat_provider"),
        Index("ix_dl_source_catalog", "catalog_id"),
        Index("ix_dl_source_provider", "provider_type"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(
        String(32), default="api", nullable=False,
    )
    endpoint_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ingestion_method: Mapped[str] = mapped_column(
        String(32), default="full_refresh", nullable=False,
    )
    frequency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    auth_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    catalog: Mapped["DataLakeCatalog"] = relationship()
    ingestion_runs: Mapped[list["DataLakeIngestionRun"]] = relationship(
        back_populates="source", cascade="all, delete-orphan",
    )


class DataLakeIngestionRun(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_ingestion_runs"
    __table_args__ = (
        Index("ix_dl_ingest_source", "source_id"),
        Index("ix_dl_ingest_started", "started_at"),
        Index("ix_dl_ingest_status", "status"),
    )

    source_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_sources.id", ondelete="CASCADE"), nullable=False,
    )
    catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="SET NULL"), nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False,
    )
    rows_ingested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    source: Mapped["DataLakeSource"] = relationship(back_populates="ingestion_runs")


class DataLakeSnapshot(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_snapshots"
    __table_args__ = (
        UniqueConstraint("catalog_id", "label", name="uq_dl_snap_cat_label"),
        Index("ix_dl_snapshot_catalog", "catalog_id"),
        Index("ix_dl_snapshot_version", "version_id"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("datalake_versions.id", ondelete="SET NULL"), nullable=True,
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_path: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_restore_point: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    catalog: Mapped["DataLakeCatalog"] = relationship()
    version_ref: Mapped["DataLakeVersion | None"] = relationship()


class DataLakeDiff(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datalake_diffs"
    __table_args__ = (
        Index("ix_dl_diff_catalog", "catalog_id"),
        Index("ix_dl_diff_versions", "source_version_id", "target_version_id"),
    )

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_catalog.id", ondelete="CASCADE"), nullable=False,
    )
    source_version_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_versions.id", ondelete="CASCADE"), nullable=False,
    )
    target_version_id: Mapped[int] = mapped_column(
        ForeignKey("datalake_versions.id", ondelete="CASCADE"), nullable=False,
    )
    source_version: Mapped[str] = mapped_column(String(16), nullable=False)
    target_version: Mapped[str] = mapped_column(String(16), nullable=False)
    added_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    modified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_column: Mapped[str | None] = mapped_column(String(128), nullable=True)

    catalog: Mapped["DataLakeCatalog"] = relationship()
    source_version_ref: Mapped["DataLakeVersion"] = relationship(
        foreign_keys=[source_version_id],
    )
    target_version_ref: Mapped["DataLakeVersion"] = relationship(
        foreign_keys=[target_version_id],
    )
