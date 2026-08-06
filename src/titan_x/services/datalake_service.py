"""Data Lake management service facade.

Orchestrates dataset registration, versioning, schema management,
pipeline execution, lineage tracking, archival, and metadata across
the 8 data-lake layers: raw, validated, normalized, features,
predictions, archives, metadata, staging.

The concrete behaviour lives in the domain mixins under
:mod:`titan_x.services.datalake`; this module composes them and keeps the
historical import path ``titan_x.services.datalake_service`` working.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.data_lake import (
    DataLakeCatalog,
    DataLakePipeline,
    DataLakeSource,
)
from titan_x.services.datalake import (
    ArchiveMixin,
    CatalogMixin,
    ChecksumMixin,
    DiffMixin,
    IngestionMixin,
    LineageMixin,
    MetadataMixin,
    MoveDataMixin,
    PipelineMixin,
    SchemaMixin,
    SnapshotMixin,
    SourceMixin,
    StorageMixin,
    VersionMixin,
)
from titan_x.services.datalake.constants import (
    PIPELINE_STATUSES,
    VALID_TRANSFORMATIONS,
    _serialize_dt,
    _validate_layer,
)

__all__ = [
    "DataLakeService",
    "PIPELINE_STATUSES",
    "VALID_TRANSFORMATIONS",
    "_serialize_dt",
    "_validate_layer",
]


class DataLakeService(
    CatalogMixin,
    SchemaMixin,
    VersionMixin,
    PipelineMixin,
    LineageMixin,
    MetadataMixin,
    ArchiveMixin,
    StorageMixin,
    MoveDataMixin,
    SourceMixin,
    IngestionMixin,
    SnapshotMixin,
    DiffMixin,
    ChecksumMixin,
):
    """Service for managing the data lake catalog, storage, and pipelines."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Internals ────────────────────────────────────────────────────────

    async def _find_catalog(
        self,
        name: str,
        layer: str,
    ) -> DataLakeCatalog | None:
        result = await self.session.execute(
            select(DataLakeCatalog).where(
                DataLakeCatalog.name == name,
                DataLakeCatalog.layer == layer,
            )
        )
        return result.scalar_one_or_none()

    async def _get_pipeline(
        self,
        pipeline_id: int,
    ) -> DataLakePipeline | None:
        result = await self.session.execute(
            select(DataLakePipeline).where(DataLakePipeline.id == pipeline_id)
        )
        return result.scalar_one_or_none()

    async def _find_source(
        self,
        catalog_id: int,
        provider_name: str,
    ) -> DataLakeSource | None:
        result = await self.session.execute(
            select(DataLakeSource).where(
                DataLakeSource.catalog_id == catalog_id,
                DataLakeSource.provider_name == provider_name,
            )
        )
        return result.scalar_one_or_none()
