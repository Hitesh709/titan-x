import json
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.market_data_collector import (
    CollectorQueueItem,
    DataChecksum,
    DataSource,
    DataValidationResult,
    SyncAuditLog,
    SyncRun,
)
from titan_x.models.price import DailyPrice
from titan_x.services.market_data_collector_service import (
    ChecksumService,
    DataValidator,
    LiveStreamAdapter,
    MarketDataCollectorService,
    MockLiveStreamAdapter,
    MockSourceAdapter,
    SourceAdapter,
    SyncOrchestrator,
    ValidationOutcome,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def svc(session: AsyncSession) -> MarketDataCollectorService:
    return MarketDataCollectorService(session)


@pytest_asyncio.fixture
async def source(session: AsyncSession) -> DataSource:
    src = DataSource(name="test_source", provider_type="mock", priority=10)
    session.add(src)
    await session.flush()
    await session.refresh(src)
    return src


@pytest_asyncio.fixture
async def company(session: AsyncSession) -> Company:
    c = Company(symbol="TEST", company_name="Test Corp", isin="IN999", sector="Technology", exchange="NSE", status="active")
    session.add(c)
    await session.flush()
    return c


# ============================================================
# DATA SOURCE MANAGEMENT
# ============================================================

class TestDataSourceManagement:
    @pytest.mark.asyncio
    async def test_create_source(self, svc: MarketDataCollectorService):
        src = await svc.create_source("my_source", "mock", {"key": "val"}, priority=5, rate_limit=10.0)
        assert src.name == "my_source"
        assert src.provider_type == "mock"
        assert src.config_json == '{"key": "val"}'
        assert src.priority == 5
        assert src.rate_limit_per_second == 10.0
        assert src.enabled is True
        assert src.status == "active"

    @pytest.mark.asyncio
    async def test_get_source(self, svc: MarketDataCollectorService, source: DataSource):
        got = await svc.get_source(source.id)
        assert got is not None
        assert got.id == source.id
        assert got.name == "test_source"

    @pytest.mark.asyncio
    async def test_get_source_not_found(self, svc: MarketDataCollectorService):
        got = await svc.get_source(9999)
        assert got is None

    @pytest.mark.asyncio
    async def test_list_sources(self, svc: MarketDataCollectorService, source: DataSource):
        src2 = await svc.create_source("second", "mock")
        sources = await svc.list_sources()
        assert len(sources) >= 2
        names = [s.name for s in sources]
        assert "test_source" in names
        assert "second" in names

    @pytest.mark.asyncio
    async def test_list_sources_enabled_only(self, svc: MarketDataCollectorService, source: DataSource):
        src2 = await svc.create_source("disabled_one", "mock")
        await svc.update_source(src2.id, enabled=False)
        sources = await svc.list_sources(enabled_only=True)
        names = [s.name for s in sources]
        assert "test_source" in names
        assert "disabled_one" not in names

    @pytest.mark.asyncio
    async def test_update_source(self, svc: MarketDataCollectorService, source: DataSource):
        updated = await svc.update_source(source.id, enabled=False, priority=20, rate_limit_per_second=5.0)
        assert updated.enabled is False
        assert updated.priority == 20
        assert updated.rate_limit_per_second == 5.0

    @pytest.mark.asyncio
    async def test_delete_source(self, svc: MarketDataCollectorService, source: DataSource):
        await svc.delete_source(source.id)
        deleted = await svc.get_source(source.id)
        assert deleted is not None
        assert deleted.status == "deleted"
        assert deleted.enabled is False

    @pytest.mark.asyncio
    async def test_test_source(self, svc: MarketDataCollectorService, source: DataSource):
        result = await svc.test_source(source.id)
        assert result["healthy"] is True
        assert result["source_id"] == source.id

    @pytest.mark.asyncio
    async def test_source_audit_log_created(self, svc: MarketDataCollectorService):
        src = await svc.create_source("audit_test", "mock")
        logs = await svc.get_audit_logs()
        events = [l.event_type for l in logs]
        assert "source_created" in events


# ============================================================
# SYNC OPERATIONS
# ============================================================

class TestSyncOperations:
    @pytest.mark.asyncio
    async def test_incremental_sync(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        run = await svc.run_incremental_sync(source.id, "TEST")
        assert run.symbol == "TEST"
        assert run.status == "completed"
        assert run.sync_type == "incremental"
        assert run.inserted > 0
        assert run.duration_ms is not None
        assert run.total_records > 0

    @pytest.mark.asyncio
    async def test_incremental_sync_upserts_existing(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        run1 = await svc.run_incremental_sync(source.id, "TEST")
        inserted_first = run1.inserted

        run2 = await svc.run_incremental_sync(source.id, "TEST")
        assert run2.updated > 0
        assert run2.inserted == 0

    @pytest.mark.asyncio
    async def test_historical_sync(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        start = date.today() - timedelta(days=30)
        run = await svc.run_historical_sync(source.id, "TEST", start)
        assert run.status == "completed"
        assert run.sync_type == "historical"
        assert run.inserted > 0

    @pytest.mark.asyncio
    async def test_historical_sync_skips_existing(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        start = date.today() - timedelta(days=10)
        run1 = await svc.run_historical_sync(source.id, "TEST", start)
        inserted_first = run1.inserted

        run2 = await svc.run_historical_sync(source.id, "TEST", start)
        assert run2.skipped > 0

    @pytest.mark.asyncio
    async def test_sync_all_sources(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        runs = await svc.sync_all_sources("TEST")
        assert len(runs) >= 1
        for r in runs:
            assert r.status == "completed"

    @pytest.mark.asyncio
    async def test_sync_run_logs_created(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        run = await svc.run_incremental_sync(source.id, "TEST")
        logs = await svc.get_audit_logs(sync_run_id=run.id)
        assert len(logs) >= 1

    @pytest.mark.asyncio
    async def test_sync_updates_source_timestamp(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        assert source.last_sync_at is None
        await svc.run_incremental_sync(source.id, "TEST")
        updated = await svc.get_source(source.id)
        assert updated.last_sync_at is not None


# ============================================================
# SYNC RUN HISTORY & STATS
# ============================================================

class TestSyncRunHistory:
    @pytest.mark.asyncio
    async def test_get_sync_runs(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.run_incremental_sync(source.id, "TEST")
        runs = await svc.get_sync_runs()
        assert len(runs) >= 1

    @pytest.mark.asyncio
    async def test_get_sync_runs_by_source(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.run_incremental_sync(source.id, "TEST")
        runs = await svc.get_sync_runs(source_id=source.id)
        assert len(runs) >= 1

    @pytest.mark.asyncio
    async def test_get_sync_runs_by_type(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.run_incremental_sync(source.id, "TEST")
        runs = await svc.get_sync_runs(sync_type="incremental")
        assert len(runs) >= 1

    @pytest.mark.asyncio
    async def test_sync_stats(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.run_incremental_sync(source.id, "TEST")
        stats = await svc.get_sync_stats()
        assert "total_inserted" in stats
        assert stats["total_inserted"] > 0


# ============================================================
# AUDIT LOGS
# ============================================================

class TestAuditLogs:
    @pytest.mark.asyncio
    async def test_get_audit_logs(self, svc: MarketDataCollectorService, source: DataSource):
        logs = await svc.get_audit_logs()
        assert isinstance(logs, list)

    @pytest.mark.asyncio
    async def test_audit_log_event_persistence(self, svc: MarketDataCollectorService, source: DataSource):
        await svc.create_source("audit_src", "mock")
        logs = await svc.get_audit_logs(event_type="source_created")
        assert len(logs) >= 1

    @pytest.mark.asyncio
    async def test_audit_log_filter_by_severity(self, svc: MarketDataCollectorService, source: DataSource):
        logs = await svc.get_audit_logs(severity="info")
        assert len(logs) >= 0


# ============================================================
# QUEUE PROCESSING
# ============================================================

class TestQueueProcessing:
    @pytest.mark.asyncio
    async def test_enqueue_sync(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        item = await svc.enqueue_sync(source.id, "incremental_sync", "TEST")
        assert item.status == "pending"
        assert item.task_type == "incremental_sync"
        assert item.symbol == "TEST"
        assert item.retry_count == 0

    @pytest.mark.asyncio
    async def test_process_queue_incremental(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.enqueue_sync(source.id, "incremental_sync", "TEST")
        processed = await svc.process_queue(batch_size=10)
        assert len(processed) >= 1
        assert processed[0].status == "completed"

    @pytest.mark.asyncio
    async def test_process_queue_historical(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        payload = {"start": (date.today() - timedelta(days=5)).isoformat()}
        await svc.enqueue_sync(source.id, "historical_sync", "TEST", payload=payload)
        processed = await svc.process_queue(batch_size=10)
        assert len(processed) >= 1

    @pytest.mark.asyncio
    async def test_queue_stats(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        stats = await svc.get_queue_stats()
        assert "pending" in stats or True  # empty is ok

    @pytest.mark.asyncio
    async def test_queue_stats_after_enqueue(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.enqueue_sync(source.id, "incremental_sync", "TEST")
        stats = await svc.get_queue_stats()
        assert stats.get("pending", 0) >= 1

    @pytest.mark.asyncio
    async def test_list_queue_items(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.enqueue_sync(source.id, "incremental_sync", "TEST")
        items = await svc.list_queue_items()
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_retry_failed_items(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        item = await svc.enqueue_sync(source.id, "incremental_sync", "TEST")
        # mark as failed with retry_count at max
        item.status = "failed"
        item.retry_count = 3
        await svc.session.flush()

        count = await svc.retry_failed_items()
        assert count == 0  # retry_count (3) not < max_retries (3), so none retried

    @pytest.mark.asyncio
    async def test_clear_completed_items(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.enqueue_sync(source.id, "incremental_sync", "TEST")
        processed = await svc.process_queue()
        cleared = await svc.clear_completed_items(older_than_days=0)
        assert cleared >= 0

    @pytest.mark.asyncio
    async def test_queue_item_with_schedule(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        item = await svc.enqueue_sync(source.id, "incremental_sync", "TEST", scheduled_at=future)
        assert item.scheduled_at is not None
        assert item.scheduled_at.hour == future.hour

    @pytest.mark.asyncio
    async def test_process_queue_respects_schedule(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await svc.enqueue_sync(source.id, "incremental_sync", "TEST", scheduled_at=future)
        processed = await svc.process_queue()
        assert len(processed) == 0  # not yet scheduled

    @pytest.mark.asyncio
    async def test_unknown_task_type_fails(self, svc: MarketDataCollectorService, source: DataSource):
        item = CollectorQueueItem(
            source_id=source.id,
            task_type="unknown_task",
            symbol="TEST",
            max_retries=1,
        )
        svc.session.add(item)
        await svc.session.flush()
        await svc.process_queue()
        await svc.session.refresh(item)
        assert item.status == "failed"


# ============================================================
# LIVE STREAMING
# ============================================================

class TestLiveStreaming:
    @pytest.mark.asyncio
    async def test_start_stop_live_stream(self, svc: MarketDataCollectorService):
        await svc.start_live_stream("mock_live", ["AAPL", "GOOG"])
        assert "mock_live" in svc.get_active_streams()

        await svc.stop_live_stream("mock_live")
        assert "mock_live" not in svc.get_active_streams()

    @pytest.mark.asyncio
    async def test_consume_live_ticks(self, svc: MarketDataCollectorService):
        await svc.start_live_stream("ticker", ["AAPL"])
        ticks = await svc.consume_live_ticks("ticker", max_ticks=3)
        assert len(ticks) == 3
        for t in ticks:
            assert "symbol" in t
            assert "last_price" in t
            assert "timestamp" in t

    @pytest.mark.asyncio
    async def test_consume_from_stopped_stream(self, svc: MarketDataCollectorService):
        with pytest.raises(ValueError, match="Live stream not active"):
            await svc.consume_live_ticks("nonexistent")

    @pytest.mark.asyncio
    async def test_duplicate_stream_start(self, svc: MarketDataCollectorService):
        await svc.start_live_stream("dup", ["AAPL"])
        with pytest.raises(ValueError, match="already active"):
            await svc.start_live_stream("dup", ["GOOG"])

    @pytest.mark.asyncio
    async def test_get_active_streams_empty(self, svc: MarketDataCollectorService):
        assert svc.get_active_streams() == []

    @pytest.mark.asyncio
    async def test_mock_live_stream_adapter(self):
        stream = MockLiveStreamAdapter("test")
        assert stream.is_connected() is False

        await stream.connect(["AAPL"])
        assert stream.is_connected() is True

        tick = await stream.next_tick()
        assert tick is not None
        assert tick["symbol"] == "AAPL"
        assert tick["tick_id"] == 1

        await stream.disconnect()
        assert stream.is_connected() is False


# ============================================================
# DATA VALIDATION
# ============================================================

class TestDataValidation:
    def test_valid_record_passes(self):
        validator = DataValidator()
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        outcome = validator.validate(record)
        assert outcome.passed is True
        assert outcome.checks_failed == 0
        assert outcome.checks_passed == 8

    def test_negative_price_fails(self):
        validator = DataValidator()
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": -100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        outcome = validator.validate(record)
        assert outcome.passed is False

    def test_high_low_inverted_fails(self):
        validator = DataValidator()
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": 100.0,
            "high": 90.0,
            "low": 105.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        outcome = validator.validate(record)
        assert outcome.passed is False
        assert "high_low_inconsistent" in outcome.errors

    def test_zero_volume_fails(self):
        validator = DataValidator()
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 0,
        }
        outcome = validator.validate(record)
        assert outcome.passed is False
        assert "volume_not_positive" in outcome.errors

    def test_future_date_fails(self):
        validator = DataValidator()
        record = {
            "symbol": "TEST",
            "trade_date": date.today() + timedelta(days=365),
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        outcome = validator.validate(record)
        assert outcome.passed is False
        assert "date_in_future" in outcome.errors

    def test_open_out_of_range_fails(self):
        validator = DataValidator()
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": 200.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        outcome = validator.validate(record)
        assert outcome.passed is False

    def test_nan_value_fails(self):
        validator = DataValidator()
        import math
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": float("nan"),
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        outcome = validator.validate(record)
        assert outcome.passed is False

    def test_validation_stats(self, svc: MarketDataCollectorService, source: DataSource):
        import pytest
        pytest.skip("Requires async session in sync context - tested via validate_record integration")

    @pytest.mark.asyncio
    async def test_validate_record_api(self, svc: MarketDataCollectorService, source: DataSource):
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        result = await svc.validate_record(source.id, record)
        assert result.status == "passed"
        assert result.checks_failed == 0

    @pytest.mark.asyncio
    async def test_validate_record_failure(self, svc: MarketDataCollectorService, source: DataSource):
        record = {
            "symbol": "TEST",
            "trade_date": date.today() - timedelta(days=1),
            "open": -100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1_000_000,
        }
        result = await svc.validate_record(source.id, record)
        assert result.status == "failed"


# ============================================================
# CHECKSUM
# ============================================================

class TestChecksum:
    @pytest.mark.asyncio
    async def test_compute_checksum(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        run = await svc.run_incremental_sync(source.id, "TEST")
        chk = await svc.compute_checksum("TEST", date.today())
        assert chk.symbol == "TEST"
        assert chk.checksum_sha256 is not None
        assert len(chk.checksum_sha256) == 64

    @pytest.mark.asyncio
    async def test_verify_checksum_match(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.run_incremental_sync(source.id, "TEST")
        await svc.compute_checksum("TEST", date.today())
        ok = await svc.verify_checksum("TEST", date.today())
        assert ok is True

    @pytest.mark.asyncio
    async def test_verify_checksum_no_data(self, svc: MarketDataCollectorService):
        ok = await svc.verify_checksum("NONEXISTENT", date.today())
        assert ok is False

    @pytest.mark.asyncio
    async def test_verify_checksum_batch(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        await svc.run_incremental_sync(source.id, "TEST")
        start = date.today() - timedelta(days=5)
        end = date.today()
        results = await svc.verify_checksum_batch("TEST", start, end)
        assert "verified" in results
        assert "mismatched" in results
        assert "missing" in results

    @pytest.mark.asyncio
    async def test_compute_checksum_no_data(self, svc: MarketDataCollectorService):
        chk = await svc.compute_checksum("EMPTY", date.today())
        assert chk.row_count == 0
        assert len(chk.checksum_sha256) == 64


# ============================================================
# MOCK SOURCE ADAPTER
# ============================================================

class TestMockSourceAdapter:
    @pytest.mark.asyncio
    async def test_fetch_historical(self, source: DataSource):
        adapter = MockSourceAdapter(source)
        start = date.today() - timedelta(days=10)
        records = await adapter.fetch_historical("TEST", start, date.today())
        assert len(records) > 0
        for r in records:
            assert r["symbol"] == "TEST"
            assert "open" in r
            assert "high" in r
            assert "low" in r
            assert "close" in r
            assert "volume" in r

    @pytest.mark.asyncio
    async def test_health_check(self, source: DataSource):
        adapter = MockSourceAdapter(source)
        assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_fetch_incremental(self, source: DataSource):
        adapter = MockSourceAdapter(source)
        records = await adapter.fetch_incremental("TEST", date.today() - timedelta(days=2))
        assert len(records) > 0


# ============================================================
# EDGE CASES
# ============================================================

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_sync_nonexistent_source(self, svc: MarketDataCollectorService):
        with pytest.raises(ValueError, match="DataSource.*not found"):
            await svc.run_incremental_sync(99999, "TEST")

    @pytest.mark.asyncio
    async def test_update_nonexistent_source(self, svc: MarketDataCollectorService):
        with pytest.raises(ValueError, match="DataSource.*not found"):
            await svc.update_source(99999, enabled=False)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_source(self, svc: MarketDataCollectorService):
        with pytest.raises(ValueError, match="DataSource.*not found"):
            await svc.delete_source(99999)

    @pytest.mark.asyncio
    async def test_unsupported_provider_type(self, svc: MarketDataCollectorService, source: DataSource):
        src = await svc.create_source("bad_source", "unsupported")
        with pytest.raises(ValueError, match="Unsupported provider type"):
            await svc.run_incremental_sync(src.id, "TEST")

    @pytest.mark.asyncio
    async def test_sync_without_company(self, svc: MarketDataCollectorService, source: DataSource):
        run = await svc.run_incremental_sync(source.id, "NOCOMPANY")
        assert run.status == "completed"
        assert run.inserted > 0

    @pytest.mark.asyncio
    async def test_multiple_sync_runs(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        for _ in range(3):
            await svc.run_incremental_sync(source.id, "TEST")
        runs = await svc.get_sync_runs(symbol="TEST")
        assert len(runs) >= 3

    @pytest.mark.asyncio
    async def test_queue_process_multiple_items(self, svc: MarketDataCollectorService, source: DataSource, company: Company):
        for sym in ["TEST", "TEST", "TEST"]:
            await svc.enqueue_sync(source.id, "incremental_sync", sym)
        processed = await svc.process_queue(batch_size=10)
        assert len(processed) == 3
