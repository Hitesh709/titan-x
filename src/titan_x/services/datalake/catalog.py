"""Catalog, schema, and versioning mixins for :class:`DataLakeService`."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from titan_x.models.data_lake import (
    DataLakeCatalog,
    DataLakeSchema,
    DataLakeVersion,
)
from titan_x.services import datalake_storage as storage
from titan_x.services.datalake.constants import _validate_layer


class CatalogMixin:
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
        self,
        dataset_id: int | None = None,
        name: str | None = None,
        layer: str | None = None,
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
        self,
        layer: str | None = None,
        active_only: bool = True,
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
        self,
        dataset_id: int,
        **kwargs: Any,
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
        self,
        dataset_id: int,
        remove_files: bool = False,
    ) -> bool:
        entry = await self.get_dataset(dataset_id=dataset_id)
        if not entry:
            return False
        if remove_files:
            storage.delete_dataset(entry.layer, entry.name)
        await self.session.delete(entry)
        await self.session.commit()
        return True


class SchemaMixin:
    async def register_schema(
        self,
        catalog_id: int,
        schema_def: dict[str, Any],
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
        self,
        catalog_id: int,
        version: str | None = None,
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


class VersionMixin:
    async def create_version(
        self,
        catalog_id: int,
        version: str,
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
        self,
        catalog_id: int,
        version: str,
    ) -> DataLakeVersion | None:
        result = await self.session.execute(
            select(DataLakeVersion).where(
                DataLakeVersion.catalog_id == catalog_id,
                DataLakeVersion.version == version,
            )
        )
        return result.scalar_one_or_none()
