"""Archive, storage, and data-movement mixins for :class:`DataLakeService`."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from titan_x.models.data_lake import DataLakeArchive, DataLakeStorageRecord
from titan_x.services import datalake_storage as storage
from titan_x.services.datalake.constants import _validate_layer


class ArchiveMixin:
    async def archive_dataset(
        self,
        catalog_id: int,
        archive_format: str = "parquet",
        retention_days: int = 365,
        partition_start: date | None = None,
        partition_end: date | None = None,
    ) -> DataLakeArchive:
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
            "archives",
            cat.name,
            rows,
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
        self,
        catalog_id: int | None = None,
    ) -> list[DataLakeArchive]:
        stmt = select(DataLakeArchive).where(
            DataLakeArchive.is_deleted.is_(False),
        )
        if catalog_id:
            stmt = stmt.where(DataLakeArchive.catalog_id == catalog_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class StorageMixin:
    async def store_records(
        self,
        layer: str,
        dataset_name: str,
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
        self,
        layer: str,
        dataset_name: str,
        partition_date: date | None = None,
        version: str | None = None,
    ) -> list[dict[str, Any]]:
        return storage.load_dataset(layer, dataset_name, partition_date, version)

    async def get_storage_stats(self) -> dict[str, Any]:
        return storage.get_storage_stats()


class MoveDataMixin:
    async def move_data(
        self,
        source_catalog_id: int,
        target_catalog_id: int,
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
            dst.layer,
            dst.name,
            rows,
            partition_date,
        )

        src.row_count = len(rows)
        dst.row_count = len(rows)
        dst.total_size_bytes = meta["file_size"]

        if pipeline_id:
            await self.complete_pipeline(
                pipeline_id,
                rows_read=len(rows),
                rows_written=len(rows),
            )

        await self.record_lineage(
            source_catalog_id,
            target_catalog_id,
            transformation=transformation,
            pipeline_id=pipeline_id,
        )

        await self.session.commit()
        return {"rows_moved": len(rows), "status": "ok"}
