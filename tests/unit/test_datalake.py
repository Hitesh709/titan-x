"""Tests for the Data Lake: catalog, storage, service, versioning, pipelines, lineage, archival, metadata.

Covers all 8 layers (raw, validated, normalized, features, predictions, archives, metadata, staging)
and every model.  Uses a temporary directory for file storage and a fresh in-memory SQLite database.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
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
from titan_x.services.datalake_service import DataLakeService
from titan_x.services import datalake_storage as storage


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_local = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_local() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session

    await engine.dispose()


from sqlalchemy import text  # noqa: E402


@pytest_asyncio.fixture
async def service(db_session: AsyncSession) -> DataLakeService:
    return DataLakeService(db_session)


@pytest.fixture(autouse=True)
def temp_lake_dir():
    with tempfile.TemporaryDirectory() as tmp:
        old = storage.BASE_LAKE_DIR
        storage.BASE_LAKE_DIR = tmp
        yield
        storage.BASE_LAKE_DIR = old


# ── Layer validation ─────────────────────────────────────────────────────────


class TestDataLakeLayers:
    def test_all_layers_present(self):
        assert "raw" in DATALAKE_LAYERS
        assert "validated" in DATALAKE_LAYERS
        assert "normalized" in DATALAKE_LAYERS
        assert "features" in DATALAKE_LAYERS
        assert "predictions" in DATALAKE_LAYERS
        assert "archives" in DATALAKE_LAYERS
        assert "metadata" in DATALAKE_LAYERS
        assert "staging" in DATALAKE_LAYERS

    def test_layer_count(self):
        assert len(DATALAKE_LAYERS) == 8


# ── Storage tests ────────────────────────────────────────────────────────────


class TestDataLakeStorage:
    def test_save_and_load_json(self):
        rows = [{"symbol": "AAPL", "close": 150.0, "date": "2026-07-20"}]
        meta = storage.save_dataset("raw", "test_prices", rows, fmt="json")
        assert meta["row_count"] == 1
        assert meta["file_format"] == "json"
        assert os.path.isfile(meta["storage_path"])

        loaded = storage.load_dataset("raw", "test_prices")
        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "AAPL"

    def test_save_and_load_csv(self):
        rows = [
            {"symbol": "AAPL", "close": "150.0"},
            {"symbol": "GOOG", "close": "2800.0"},
        ]
        meta = storage.save_dataset("raw", "test_csv", rows, fmt="csv")
        assert meta["row_count"] == 2

        loaded = storage.load_dataset("raw", "test_csv")
        assert len(loaded) == 2
        assert loaded[1]["symbol"] == "GOOG"

    def test_load_nonexistent(self):
        loaded = storage.load_dataset("raw", "nonexistent")
        assert loaded == []

    def test_save_with_partition_date(self):
        rows = [{"symbol": "AAPL", "close": 150.0}]
        meta = storage.save_dataset(
            "raw", "partitioned", rows, partition_date=date(2026, 7, 20), fmt="json",
        )
        assert "dt=2026-07-20" in meta["storage_path"]

    def test_save_with_version(self):
        rows = [{"symbol": "AAPL", "close": 150.0}]
        meta = storage.save_dataset(
            "features", "rsi", rows, version="2.0.0", fmt="json",
        )
        assert "ver=2.0.0" in meta["storage_path"]

    def test_list_datasets(self):
        storage.save_dataset("raw", "ds1", [{"x": 1}], fmt="json")
        storage.save_dataset("raw", "ds2", [{"x": 2}], fmt="json")
        datasets = storage.list_datasets("raw")
        names = {d["name"] for d in datasets}
        assert names == {"ds1", "ds2"}

    def test_delete_dataset(self):
        storage.save_dataset("raw", "todelete", [{"x": 1}], fmt="json")
        assert storage.delete_dataset("raw", "todelete") is True
        assert storage.delete_dataset("raw", "todelete") is False

    def test_storage_stats(self):
        storage.save_dataset("raw", "a", [{"x": 1}], fmt="json")
        storage.save_dataset("features", "b", [{"x": 2}], fmt="json")
        stats = storage.get_storage_stats()
        assert stats["total_files"] == 2
        assert "raw" in stats["layers"]
        assert "features" in stats["layers"]

    def test_empty_storage_stats(self):
        stats = storage.get_storage_stats()
        assert stats["total_files"] == 0

    def test_save_empty_dataset(self):
        meta = storage.save_dataset("raw", "empty", [], fmt="json")
        assert meta["row_count"] == 0


# ── Service tests (catalog, schema, version, pipeline, lineage, archive) ─────


class TestDataLakeServiceCatalog:
    async def test_register_dataset(self, service):
        ds = await service.register_dataset("test_ds", "raw", description="test")
        assert ds.name == "test_ds"
        assert ds.layer == "raw"
        assert ds.is_active is True
        assert ds.id is not None

    async def test_register_duplicate_returns_existing(self, service):
        ds1 = await service.register_dataset("dup", "raw")
        ds2 = await service.register_dataset("dup", "raw")
        assert ds1.id == ds2.id

    async def test_register_invalid_layer(self, service):
        with pytest.raises(ValueError, match="Invalid layer"):
            await service.register_dataset("bad", "invalid_layer")

    async def test_get_dataset_by_id(self, service):
        ds = await service.register_dataset("getme", "raw")
        found = await service.get_dataset(dataset_id=ds.id)
        assert found is not None
        assert found.id == ds.id

    async def test_get_dataset_by_name_layer(self, service):
        await service.register_dataset("byname", "normalized")
        found = await service.get_dataset(name="byname", layer="normalized")
        assert found is not None
        assert found.name == "byname"

    async def test_get_dataset_not_found(self, service):
        assert await service.get_dataset(dataset_id=9999) is None

    async def test_list_datasets(self, service):
        await service.register_dataset("a", "raw")
        await service.register_dataset("b", "raw")
        await service.register_dataset("c", "features")
        all_ds = await service.list_datasets()
        assert len(all_ds) >= 3

    async def test_list_datasets_filter_by_layer(self, service):
        await service.register_dataset("only_raw", "raw")
        await service.register_dataset("only_features", "features")
        raw_ds = await service.list_datasets(layer="raw")
        assert all(d.layer == "raw" for d in raw_ds)

    async def test_update_dataset(self, service):
        ds = await service.register_dataset("update_me", "raw")
        updated = await service.update_dataset(ds.id, description="updated desc")
        assert updated is not None
        assert updated.description == "updated desc"

    async def test_update_dataset_not_found(self, service):
        assert await service.update_dataset(9999, description="x") is None

    async def test_delete_dataset(self, service):
        ds = await service.register_dataset("del_me", "raw")
        assert await service.delete_dataset(ds.id) is True
        assert await service.get_dataset(dataset_id=ds.id) is None

    async def test_delete_nonexistent(self, service):
        assert await service.delete_dataset(9999) is False

    async def test_delete_with_files(self, service):
        ds = await service.register_dataset("del_files", "raw")
        storage.save_dataset("raw", "del_files", [{"x": 1}], fmt="json")
        assert await service.delete_dataset(ds.id, remove_files=True) is True


class TestDataLakeServiceSchema:
    async def test_register_schema(self, service):
        ds = await service.register_dataset("schema_test", "raw")
        schema = await service.register_schema(
            ds.id, {"symbol": "string", "close": "float"}, version="1.0.0",
        )
        assert schema.catalog_id == ds.id
        assert schema.version == "1.0.0"
        schema_def = json.loads(schema.schema_definition)
        assert schema_def["symbol"] == "string"

    async def test_get_active_schema(self, service):
        ds = await service.register_dataset("active_schema", "raw")
        await service.register_schema(ds.id, {"a": "int"}, version="1.0.0")
        active = await service.get_schema(ds.id)
        assert active is not None
        assert active.version == "1.0.0"

    async def test_get_specific_version(self, service):
        ds = await service.register_dataset("specific_schema", "raw")
        await service.register_schema(ds.id, {"a": "int"}, version="1.0.0")
        await service.register_schema(ds.id, {"a": "int", "b": "str"}, version="2.0.0")
        v1 = await service.get_schema(ds.id, version="1.0.0")
        assert v1 is not None
        assert v1.version == "1.0.0"

    async def test_list_schemas(self, service):
        ds = await service.register_dataset("list_schemas", "raw")
        await service.register_schema(ds.id, {"a": "int"}, version="1.0.0")
        await service.register_schema(ds.id, {"b": "str"}, version="2.0.0")
        schemas = await service.list_schemas(ds.id)
        assert len(schemas) >= 2


class TestDataLakeServiceVersion:
    async def test_create_version(self, service):
        ds = await service.register_dataset("ver_test", "raw")
        v = await service.create_version(
            ds.id, "1.0.0", "/path/to/data", row_count=100,
            checksum="abc123",
        )
        assert v.version == "1.0.0"
        assert v.row_count == 100
        assert v.checksum == "abc123"

    async def test_list_versions(self, service):
        ds = await service.register_dataset("ver_list", "raw")
        await service.create_version(ds.id, "1.0.0", "/p1", row_count=10)
        await service.create_version(ds.id, "2.0.0", "/p2", row_count=20)
        versions = await service.list_versions(ds.id)
        assert len(versions) == 2

    async def test_get_version(self, service):
        ds = await service.register_dataset("ver_get", "raw")
        await service.create_version(ds.id, "1.0.0", "/p", row_count=5)
        v = await service.get_version(ds.id, "1.0.0")
        assert v is not None
        assert v.storage_path == "/p"


class TestDataLakeServicePipeline:
    async def test_create_pipeline(self, service):
        p = await service.create_pipeline(
            "test_pipe", "raw", "validated", pipeline_type="validate",
        )
        assert p.name == "test_pipe"
        assert p.source_layer == "raw"
        assert p.target_layer == "validated"
        assert p.status == "pending"

    async def test_create_pipeline_invalid_layer(self, service):
        with pytest.raises(ValueError):
            await service.create_pipeline("bad", "raw", "invalid")

    async def test_start_and_complete_pipeline(self, service):
        p = await service.create_pipeline("flow", "raw", "validated")
        started = await service.start_pipeline(p.id)
        assert started.status == "running"
        assert started.started_at is not None

        completed = await service.complete_pipeline(
            p.id, rows_read=50, rows_written=48, rows_failed=2,
        )
        assert completed.status == "completed"
        assert completed.rows_written == 48

    async def test_complete_with_error(self, service):
        p = await service.create_pipeline("err", "raw", "features")
        await service.start_pipeline(p.id)
        completed = await service.complete_pipeline(
            p.id, error_message="Something went wrong",
        )
        assert completed.status == "failed"
        assert completed.error_message == "Something went wrong"

    async def test_list_pipelines(self, service):
        await service.create_pipeline("p1", "raw", "validated")
        await service.create_pipeline("p2", "raw", "features")
        pipelines = await service.list_pipelines()
        assert len(pipelines) >= 2

    async def test_list_pipelines_filter_status(self, service):
        p = await service.create_pipeline("filter_me", "raw", "features")
        await service.start_pipeline(p.id)
        running = await service.list_pipelines(status="running")
        assert all(p.status == "running" for p in running)

    async def test_start_nonexistent_pipeline(self, service):
        assert await service.start_pipeline(9999) is None


class TestDataLakeServiceLineage:
    async def test_record_lineage(self, service):
        src = await service.register_dataset("src", "raw")
        dst = await service.register_dataset("dst", "validated")
        ln = await service.record_lineage(src.id, dst.id, transformation="validate")
        assert ln.source_catalog_id == src.id
        assert ln.target_catalog_id == dst.id
        assert ln.transformation == "validate"

    async def test_record_lineage_invalid_transformation(self, service):
        src = await service.register_dataset("src2", "raw")
        dst = await service.register_dataset("dst2", "validated")
        with pytest.raises(ValueError):
            await service.record_lineage(src.id, dst.id, transformation="unknown")

    async def test_get_downstream(self, service):
        raw = await service.register_dataset("raw_ds", "raw")
        val = await service.register_dataset("val_ds", "validated")
        feat = await service.register_dataset("feat_ds", "features")
        await service.record_lineage(raw.id, val.id, transformation="validate")
        await service.record_lineage(val.id, feat.id, transformation="feature_engineer")

        downstream = await service.get_downstream(raw.id)
        assert len(downstream) == 1
        assert downstream[0].target_catalog_id == val.id

    async def test_get_upstream(self, service):
        raw = await service.register_dataset("raw_up", "raw")
        val = await service.register_dataset("val_up", "validated")
        await service.record_lineage(raw.id, val.id, transformation="validate")
        upstream = await service.get_upstream(val.id)
        assert len(upstream) == 1
        assert upstream[0].source_catalog_id == raw.id

    async def test_get_lineage_graph(self, service):
        raw = await service.register_dataset("graph_src", "raw")
        val = await service.register_dataset("graph_dst", "validated")
        await service.record_lineage(raw.id, val.id, transformation="validate")
        graph = await service.get_lineage_graph(raw.id)
        assert len(graph["nodes"]) >= 2
        assert len(graph["edges"]) >= 1


class TestDataLakeServiceMetadata:
    async def test_set_and_get_metadata(self, service):
        ds = await service.register_dataset("meta_ds", "raw")
        m = await service.set_metadata(ds.id, "row_count", "1500", "integer")
        assert m.metric_name == "row_count"
        assert m.metric_value == "1500"

        results = await service.get_metadata(ds.id)
        assert len(results) == 1

    async def test_get_metadata_filter_by_name(self, service):
        ds = await service.register_dataset("meta_filter", "raw")
        await service.set_metadata(ds.id, "min_price", "100")
        await service.set_metadata(ds.id, "max_price", "200")
        results = await service.get_metadata(ds.id, metric_name="min_price")
        assert len(results) == 1
        assert results[0].metric_value == "100"


class TestDataLakeServiceArchive:
    async def test_archive_dataset(self, service):
        ds = await service.register_dataset("archive_me", "raw")
        storage.save_dataset("raw", "archive_me", [
            {"symbol": "AAPL", "close": 150},
            {"symbol": "GOOG", "close": 2800},
        ], fmt="json")
        archive = await service.archive_dataset(
            ds.id, retention_days=90, partition_start=date(2026, 1, 1),
        )
        assert archive.row_count == 2
        assert archive.retention_until is not None
        assert archive.catalog_id == ds.id

    async def test_archive_nonexistent_dataset(self, service):
        with pytest.raises(ValueError):
            await service.archive_dataset(9999)

    async def test_list_archives(self, service):
        ds = await service.register_dataset("archive_list", "raw")
        storage.save_dataset("raw", "archive_list", [{"x": 1}], fmt="json")
        await service.archive_dataset(ds.id)
        archives = await service.list_archives()
        assert len(archives) >= 1

    async def test_list_archives_by_catalog(self, service):
        ds1 = await service.register_dataset("arch_cat1", "raw")
        ds2 = await service.register_dataset("arch_cat2", "raw")
        storage.save_dataset("raw", "arch_cat1", [{"x": 1}], fmt="json")
        storage.save_dataset("raw", "arch_cat2", [{"x": 2}], fmt="json")
        await service.archive_dataset(ds1.id)
        await service.archive_dataset(ds2.id)
        archives = await service.list_archives(catalog_id=ds1.id)
        assert len(archives) == 1


class TestDataLakeServiceStorage:
    async def test_store_records(self, service, db_session):
        ds = await service.register_dataset("store_rec", "raw")
        rec = await service.store_records(
            "raw", "store_rec",
            [{"symbol": "AAPL", "close": 150}],
            partition_date=date(2026, 7, 20),
            fmt="json",
            catalog_id=ds.id,
        )
        assert rec.row_count == 1
        assert rec.file_format == "json"
        assert rec.layer == "raw"
        assert rec.storage_path is not None

    async def test_load_records(self, service):
        await service.register_dataset("load_rec", "raw")
        await service.store_records(
            "raw", "load_rec", [{"symbol": "AAPL"}], fmt="json",
        )
        loaded = await service.load_records("raw", "load_rec")
        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "AAPL"

    async def test_load_nonexistent_records(self, service):
        loaded = await service.load_records("raw", "no_such_dataset")
        assert loaded == []

    async def test_store_invalid_layer(self, service):
        with pytest.raises(ValueError):
            await service.store_records("bad_layer", "x", [{"a": 1}])

    async def test_storage_stats(self, service):
        await service.store_records(
            "raw", "stats_test", [{"x": 1}], fmt="json",
        )
        stats = await service.get_storage_stats()
        assert stats["total_files"] >= 1


class TestDataLakeServiceMoveData:
    async def test_move_data_between_datasets(self, service):
        src = await service.register_dataset("move_src", "raw")
        dst = await service.register_dataset("move_dst", "validated")
        storage.save_dataset("raw", "move_src", [
            {"symbol": "AAPL", "close": 150},
        ], fmt="json")

        result = await service.move_data(src.id, dst.id, transformation="validate")
        assert result["rows_moved"] == 1
        assert result["status"] == "ok"

    async def test_move_data_no_source_data(self, service):
        src = await service.register_dataset("empty_src", "raw")
        dst = await service.register_dataset("empty_dst", "validated")
        result = await service.move_data(src.id, dst.id)
        assert result["status"] == "no_data"

    async def test_move_nonexistent_source(self, service):
        dst = await service.register_dataset("orphan_dst", "raw")
        with pytest.raises(ValueError):
            await service.move_data(9999, dst.id)


# ── Model ORM tests ──────────────────────────────────────────────────────────


class TestDataLakeModels:
    async def test_create_catalog_entry(self, db_session):
        entry = DataLakeCatalog(
            name="test_model", layer="raw", storage_path="/tmp/test",
        )
        db_session.add(entry)
        await db_session.commit()

        result = await db_session.execute(
            select(DataLakeCatalog).where(DataLakeCatalog.name == "test_model"),
        )
        found = result.scalar_one()
        assert found.layer == "raw"
        assert found.is_active is True

    async def test_catalog_unique_constraint(self, db_session):
        from sqlalchemy import select

        db_session.add(DataLakeCatalog(name="uniq", layer="raw", storage_path="/a"))
        await db_session.commit()

        db_session.add(DataLakeCatalog(name="uniq", layer="raw", storage_path="/b"))
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()

    async def test_pipeline_relations(self, db_session):
        src = DataLakeCatalog(name="pipe_src", layer="raw", storage_path="/s")
        dst = DataLakeCatalog(name="pipe_dst", layer="validated", storage_path="/d")
        db_session.add_all([src, dst])
        await db_session.commit()

        pipe = DataLakePipeline(
            name="relation_pipe",
            source_layer="raw", target_layer="validated",
            source_catalog_id=src.id, target_catalog_id=dst.id,
        )
        db_session.add(pipe)
        await db_session.commit()

        ln = DataLakeLineage(
            source_catalog_id=src.id, target_catalog_id=dst.id,
            pipeline_id=pipe.id, transformation="validate",
        )
        db_session.add(ln)
        await db_session.commit()

        result = await db_session.execute(
            select(DataLakeLineage).where(DataLakeLineage.pipeline_id == pipe.id),
        )
        found = result.scalar_one()
        assert found.transformation == "validate"


# ── Source tracking tests ──────────────────────────────────────────────────


class TestDataLakeSourceTracking:
    async def test_register_source(self, service):
        ds = await service.register_dataset("src_track", "raw")
        src = await service.register_source(
            catalog_id=ds.id,
            provider_name="alpha_vantage",
            provider_type="api",
            endpoint_url="https://www.alphavantage.co/query",
            ingestion_method="incremental",
            frequency="daily",
        )
        assert src.provider_name == "alpha_vantage"
        assert src.ingestion_method == "incremental"
        assert src.is_active is True
        assert src.id is not None

    async def test_register_source_invalid_catalog(self, service):
        with pytest.raises(ValueError):
            await service.register_source(9999, "test_provider")

    async def test_register_duplicate_source(self, service):
        ds = await service.register_dataset("dup_src", "raw")
        s1 = await service.register_source(ds.id, "dup_provider")
        s2 = await service.register_source(ds.id, "dup_provider")
        assert s1.id == s2.id

    async def test_get_source(self, service):
        ds = await service.register_dataset("get_src", "raw")
        src = await service.register_source(ds.id, "get_provider")
        found = await service.get_source(src.id)
        assert found is not None
        assert found.id == src.id

    async def test_get_source_not_found(self, service):
        assert await service.get_source(9999) is None

    async def test_list_sources(self, service):
        ds = await service.register_dataset("list_src", "raw")
        await service.register_source(ds.id, "src_a")
        await service.register_source(ds.id, "src_b")
        sources = await service.list_sources(catalog_id=ds.id)
        assert len(sources) == 2

    async def test_record_ingestion_success(self, service):
        ds = await service.register_dataset("ing_success", "raw")
        src = await service.register_source(ds.id, "ing_provider")
        run = await service.record_ingestion(
            source_id=src.id,
            rows_ingested=100,
            rows_failed=2,
            bytes_fetched=2048,
            checksum="abc123",
            target_version="1.0.0",
        )
        assert run.status == "completed"
        assert run.rows_ingested == 100

        # Verify source was updated
        updated = await service.get_source(src.id)
        assert updated is not None
        assert updated.last_success_at is not None
        assert updated.retry_count == 0

    async def test_record_ingestion_failure(self, service):
        ds = await service.register_dataset("ing_fail", "raw")
        src = await service.register_source(ds.id, "fail_provider")
        run = await service.record_ingestion(
            source_id=src.id,
            error_message="Connection timeout",
            rows_failed=50,
        )
        assert run.status == "failed"
        assert run.error_message == "Connection timeout"

        updated = await service.get_source(src.id)
        assert updated is not None
        assert updated.last_error_at is not None
        assert updated.last_error_message == "Connection timeout"

    async def test_list_ingestion_runs(self, service):
        ds = await service.register_dataset("ing_list", "raw")
        src = await service.register_source(ds.id, "list_provider")
        await service.record_ingestion(src.id, rows_ingested=10)
        await service.record_ingestion(src.id, rows_ingested=20)
        runs = await service.list_ingestion_runs(source_id=src.id)
        assert len(runs) == 2

    async def test_ingestion_invalid_source(self, service):
        with pytest.raises(ValueError):
            await service.record_ingestion(9999)

    async def test_source_orm_relations(self, db_session):
        cat = DataLakeCatalog(name="orm_src", layer="raw", storage_path="/p")
        db_session.add(cat)
        await db_session.commit()

        src = DataLakeSource(
            catalog_id=cat.id, provider_name="orm_provider",
        )
        db_session.add(src)
        await db_session.commit()

        run = DataLakeIngestionRun(
            source_id=src.id, catalog_id=cat.id,
            status="completed", rows_ingested=50,
        )
        db_session.add(run)
        await db_session.commit()

        result = await db_session.execute(
            select(DataLakeIngestionRun).where(
                DataLakeIngestionRun.source_id == src.id,
            )
        )
        found = result.scalar_one()
        assert found.rows_ingested == 50


# ── Snapshot / Rollback tests ─────────────────────────────────────────────


class TestDataLakeSnapshots:
    async def test_create_snapshot(self, service):
        ds = await service.register_dataset("snap_test", "raw")
        storage.save_dataset("raw", "snap_test", [
            {"id": 1, "value": "a"},
            {"id": 2, "value": "b"},
        ], fmt="json")
        await service.create_version(ds.id, "1.0.0", "/p1", row_count=2)

        snap = await service.create_snapshot(
            catalog_id=ds.id,
            version="1.0.0",
            label="pre_rollback_1",
            is_restore_point=True,
        )
        assert snap.label == "pre_rollback_1"
        assert snap.row_count == 2
        assert snap.version == "1.0.0"
        assert snap.is_restore_point is True

    async def test_create_snapshot_no_version(self, service):
        ds = await service.register_dataset("snap_nv", "raw")
        snap = await service.create_snapshot(
            catalog_id=ds.id, version="0.0.0", label="initial",
        )
        assert snap.row_count >= 0

    async def test_create_snapshot_nonexistent_catalog(self, service):
        with pytest.raises(ValueError):
            await service.create_snapshot(9999, "1.0.0", "bad")

    async def test_rollback_to_version(self, service):
        ds = await service.register_dataset("roll_test", "raw")
        storage.save_dataset("raw", "roll_test", [
            {"symbol": "AAPL", "close": 150},
            {"symbol": "GOOG", "close": 2800},
        ], fmt="json")

        v1 = await service.create_version(
            ds.id, "1.0.0", "/v1", row_count=2, checksum="c1",
        )

        # Write different data as current
        storage.save_dataset("raw", "roll_test", [
            {"symbol": "AAPL", "close": 200},
        ], fmt="json", partition_date=None, version="2.0.0")
        await service.create_version(
            ds.id, "2.0.0", "/v2", row_count=1, checksum="c2",
        )

        # Rollback to v1
        result = await service.rollback_to_version(
            catalog_id=ds.id, target_version="1.0.0",
        )
        assert result["status"] == "ok"
        assert "rollback" in result["new_version"]
        assert result["parent_version"] == "1.0.0"

        # Verify a snapshot was created
        snapshots = await service.list_snapshots(catalog_id=ds.id)
        assert len(snapshots) >= 1

    async def test_rollback_nonexistent_version(self, service):
        ds = await service.register_dataset("roll_bad", "raw")
        with pytest.raises(ValueError):
            await service.rollback_to_version(ds.id, "99.99.99")

    async def test_list_snapshots(self, service):
        ds = await service.register_dataset("snap_list", "raw")
        storage.save_dataset("raw", "snap_list", [{"x": 1}], fmt="json")
        await service.create_snapshot(ds.id, "1.0.0", "snap_a")
        await service.create_snapshot(ds.id, "1.0.0", "snap_b")
        snaps = await service.list_snapshots(catalog_id=ds.id)
        assert len(snaps) == 2

    async def test_get_snapshot(self, service):
        ds = await service.register_dataset("snap_get", "raw")
        storage.save_dataset("raw", "snap_get", [{"x": 1}], fmt="json")
        snap = await service.create_snapshot(ds.id, "1.0.0", "get_me")
        found = await service.get_snapshot(snap.id)
        assert found is not None
        assert found.label == "get_me"

    async def test_get_snapshot_not_found(self, service):
        assert await service.get_snapshot(9999) is None


# ── Diff Engine tests ─────────────────────────────────────────────────────


class TestDataLakeDiffEngine:
    async def test_compute_diff_added_and_removed(self, service):
        ds = await service.register_dataset("diff_ar", "raw")
        storage.save_dataset("raw", "diff_ar", [
            {"id": 1, "val": "a"},
            {"id": 2, "val": "b"},
        ], fmt="json", version="1.0.0")
        await service.create_version(ds.id, "1.0.0", "/v1", row_count=2, checksum="c1")

        storage.save_dataset("raw", "diff_ar", [
            {"id": 2, "val": "b"},
            {"id": 3, "val": "c"},
        ], fmt="json", version="2.0.0")
        await service.create_version(ds.id, "2.0.0", "/v2", row_count=2, checksum="c2")

        diff = await service.compute_diff(ds.id, "1.0.0", "2.0.0", key_column="id")
        assert diff.added_count == 1  # id=3 added
        assert diff.removed_count == 1  # id=1 removed
        assert diff.unchanged_count == 1  # id=2 unchanged

    async def test_compute_diff_modified(self, service):
        ds = await service.register_dataset("diff_mod", "raw")
        storage.save_dataset("raw", "diff_mod", [
            {"id": 1, "val": "old"},
        ], fmt="json", version="1.0.0")
        await service.create_version(ds.id, "1.0.0", "/v1", row_count=1, checksum="c1")

        storage.save_dataset("raw", "diff_mod", [
            {"id": 1, "val": "new"},
        ], fmt="json", version="2.0.0")
        await service.create_version(ds.id, "2.0.0", "/v2", row_count=1, checksum="c2")

        diff = await service.compute_diff(ds.id, "1.0.0", "2.0.0", key_column="id")
        assert diff.modified_count >= 1
        assert diff.unchanged_count == 0

    async def test_compute_diff_identical(self, service):
        ds = await service.register_dataset("diff_same", "raw")
        storage.save_dataset("raw", "diff_same", [
            {"id": 1, "val": "x"},
        ], fmt="json", version="1.0.0")
        await service.create_version(ds.id, "1.0.0", "/v1", row_count=1, checksum="c1")

        storage.save_dataset("raw", "diff_same", [
            {"id": 1, "val": "x"},
        ], fmt="json", version="2.0.0")
        await service.create_version(ds.id, "2.0.0", "/v2", row_count=1, checksum="c2")

        diff = await service.compute_diff(ds.id, "1.0.0", "2.0.0", key_column="id")
        assert diff.modified_count == 0
        assert diff.unchanged_count == 1

    async def test_compute_diff_auto_key(self, service):
        ds = await service.register_dataset("diff_auto", "raw")
        storage.save_dataset("raw", "diff_auto", [
            {"symbol": "AAPL", "close": 150},
        ], fmt="json", version="1.0.0")
        await service.create_version(ds.id, "1.0.0", "/v1", row_count=1, checksum="c1")

        storage.save_dataset("raw", "diff_auto", [
            {"symbol": "AAPL", "close": 155},
        ], fmt="json", version="2.0.0")
        await service.create_version(ds.id, "2.0.0", "/v2", row_count=1, checksum="c2")

        diff = await service.compute_diff(ds.id, "1.0.0", "2.0.0")
        assert diff.key_column == "symbol"
        assert diff.modified_count == 1

    async def test_compute_diff_both_empty(self, service):
        ds = await service.register_dataset("diff_empty", "raw")
        storage.save_dataset("raw", "diff_empty", [], fmt="json", version="1.0.0")
        await service.create_version(ds.id, "1.0.0", "/v1", row_count=0)
        storage.save_dataset("raw", "diff_empty", [], fmt="json", version="2.0.0")
        await service.create_version(ds.id, "2.0.0", "/v2", row_count=0)

        diff = await service.compute_diff(ds.id, "1.0.0", "2.0.0", key_column="id")
        assert diff.added_count == 0
        assert diff.removed_count == 0
        assert diff.unchanged_count == 0

    async def test_compute_diff_version_not_found(self, service):
        ds = await service.register_dataset("diff_nf", "raw")
        with pytest.raises(ValueError):
            await service.compute_diff(ds.id, "1.0.0", "2.0.0", key_column="id")

    async def test_get_diff(self, service):
        ds = await service.register_dataset("diff_get", "raw")
        storage.save_dataset("raw", "diff_get", [{"id": 1}], fmt="json", version="1.0.0")
        await service.create_version(ds.id, "1.0.0", "/v1", row_count=1)
        storage.save_dataset("raw", "diff_get", [{"id": 2}], fmt="json", version="2.0.0")
        await service.create_version(ds.id, "2.0.0", "/v2", row_count=1)
        diff = await service.compute_diff(ds.id, "1.0.0", "2.0.0", key_column="id")
        found = await service.get_diff(diff.id)
        assert found is not None
        assert found.added_count == 1
        assert found.removed_count == 1

    async def test_list_diffs(self, service):
        ds = await service.register_dataset("diff_list", "raw")
        storage.save_dataset("raw", "diff_list", [{"id": 1}], fmt="json", version="1.0.0")
        await service.create_version(ds.id, "1.0.0", "/v1", row_count=1)
        storage.save_dataset("raw", "diff_list", [{"id": 2}], fmt="json", version="2.0.0")
        await service.create_version(ds.id, "2.0.0", "/v2", row_count=1)
        await service.compute_diff(ds.id, "1.0.0", "2.0.0", key_column="id")
        diffs = await service.list_diffs()
        assert len(diffs) >= 1


# ── Checksum verification tests ────────────────────────────────────────────


class TestDataLakeChecksum:
    async def test_verify_checksum(self, service):
        ds = await service.register_dataset("chk_test", "raw")
        storage.save_dataset("raw", "chk_test", [
            {"symbol": "AAPL", "close": 150},
        ], fmt="json", version="1.0.0")
        await service.create_version(
            ds.id, "1.0.0", "/v1", row_count=1,
            checksum=storage._compute_checksum(
                b'[{"symbol": "AAPL", "close": 150}]'
            ),
        )
        result = await service.verify_checksum(ds.id, "1.0.0")
        assert result["match"] is True
        assert result["version"] == "1.0.0"

    async def test_verify_checksum_mismatch(self, service):
        ds = await service.register_dataset("chk_mismatch", "raw")
        storage.save_dataset("raw", "chk_mismatch", [
            {"symbol": "AAPL", "close": 150},
        ], fmt="json", version="1.0.0")
        await service.create_version(
            ds.id, "1.0.0", "/v1", row_count=1,
            checksum="wrongchecksum",
        )
        result = await service.verify_checksum(ds.id, "1.0.0")
        assert result["match"] is False

    async def test_verify_checksum_version_not_found(self, service):
        ds = await service.register_dataset("chk_nf", "raw")
        with pytest.raises(ValueError):
            await service.verify_checksum(ds.id, "99.99.99")


from sqlalchemy import select  # noqa: E402, F811
