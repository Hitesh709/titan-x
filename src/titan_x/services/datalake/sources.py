"""Source tracking and ingestion-run mixins for :class:`DataLakeService`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from titan_x.models.data_lake import DataLakeIngestionRun, DataLakeSource


class SourceMixin:
    async def register_source(
        self,
        catalog_id: int,
        provider_name: str,
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
        self,
        catalog_id: int | None = None,
    ) -> list[DataLakeSource]:
        stmt = select(DataLakeSource).order_by(
            DataLakeSource.provider_name,
        )
        if catalog_id:
            stmt = stmt.where(DataLakeSource.catalog_id == catalog_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class IngestionMixin:
    async def record_ingestion(
        self,
        source_id: int,
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
        self,
        source_id: int | None = None,
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
