"""Facade orchestrating sources, syncs, queue, validation, streaming and checksums."""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.market_data_collector import (
    CollectorQueueItem,
    DataChecksum,
    DataSource,
    DataValidationResult,
    SyncAuditLog,
    SyncRun,
)

from .adapters import LiveStreamAdapter, MockLiveStreamAdapter
from .checksum import ChecksumService
from .orchestrator import SyncOrchestrator
from .validation import DataValidator

logger = structlog.get_logger(__name__)


class MarketDataCollectorService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.orchestrator = SyncOrchestrator(session)
        self.validator = DataValidator()
        self.checksum = ChecksumService(session)
        self._live_streams: dict[str, LiveStreamAdapter] = {}
        self._log = logger.bind(service="market_data_collector")

    # ============================================================
    # DATA SOURCE MANAGEMENT
    # ============================================================

    async def create_source(
        self, name: str, provider_type: str, config: dict | None = None,
        priority: int = 0, rate_limit: float | None = None,
    ) -> DataSource:
        source = DataSource(
            name=name,
            provider_type=provider_type,
            config_json=json.dumps(config) if config else None,
            priority=priority,
            rate_limit_per_second=rate_limit,
        )
        self.session.add(source)
        await self.session.flush()
        await self.session.refresh(source)
        self._log.info("source_created", source_id=source.id, name=name, provider=provider_type)
        await self._audit("source_created", f"Data source '{name}' ({provider_type}) created", source.id)
        return source

    async def get_source(self, source_id: int) -> DataSource | None:
        r = await self.session.execute(
            select(DataSource).where(DataSource.id == source_id)
        )
        return r.scalar_one_or_none()

    async def list_sources(self, enabled_only: bool = False) -> list[DataSource]:
        stmt = select(DataSource).order_by(DataSource.priority.desc(), DataSource.name)
        if enabled_only:
            stmt = stmt.where(DataSource.enabled == True, DataSource.status == "active")  # noqa: E712
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def update_source(
        self, source_id: int, **kwargs: Any
    ) -> DataSource:
        source = await self.get_source(source_id)
        if not source:
            raise ValueError(f"DataSource {source_id} not found")
        allowed = {"enabled", "priority", "rate_limit_per_second", "config_json", "name", "status"}
        for k, v in kwargs.items():
            if k in allowed:
                setattr(source, k, v)
        await self.session.flush()
        await self.session.refresh(source)
        await self._audit("source_updated", f"Data source '{source.name}' updated", source_id)
        return source

    async def delete_source(self, source_id: int) -> None:
        source = await self.get_source(source_id)
        if not source:
            raise ValueError(f"DataSource {source_id} not found")
        source.status = "deleted"
        source.enabled = False
        await self.session.flush()
        await self._audit("source_deleted", f"Data source '{source.name}' deleted (soft)", source_id)

    async def test_source(self, source_id: int) -> dict[str, Any]:
        source = await self.get_source(source_id)
        if not source:
            raise ValueError(f"DataSource {source_id} not found")
        adapter = self.orchestrator._get_adapter(source)
        ok = await adapter.health_check()
        return {"source_id": source_id, "name": source.name, "healthy": ok}

    # ============================================================
    # SYNC OPERATIONS
    # ============================================================

    async def run_incremental_sync(
        self, source_id: int, symbol: str
    ) -> SyncRun:
        return await self.orchestrator.incremental_sync(source_id, symbol)

    async def run_historical_sync(
        self, source_id: int, symbol: str, start: date, end: date | None = None,
    ) -> SyncRun:
        return await self.orchestrator.historical_sync(source_id, symbol, start, end)

    async def sync_all_sources(self, symbol: str) -> list[SyncRun]:
        sources = await self.list_sources(enabled_only=True)
        runs: list[SyncRun] = []
        for src in sources:
            run = await self.orchestrator.incremental_sync(src.id, symbol)
            runs.append(run)
        return runs

    # ============================================================
    # QUEUE PROCESSING
    # ============================================================

    async def enqueue_sync(
        self, source_id: int, task_type: str, symbol: str,
        payload: dict | None = None, priority: int = 0,
        scheduled_at: datetime | None = None,
    ) -> CollectorQueueItem:
        item = CollectorQueueItem(
            source_id=source_id,
            task_type=task_type,
            symbol=symbol,
            payload_json=json.dumps(payload) if payload else None,
            priority=priority,
            scheduled_at=scheduled_at,
        )
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        self._log.info("queue_item_enqueued", item_id=item.id, task_type=task_type, symbol=symbol)
        return item

    async def process_queue(self, batch_size: int = 10) -> list[CollectorQueueItem]:
        stmt = select(CollectorQueueItem).where(
            CollectorQueueItem.status == "pending",
            (CollectorQueueItem.scheduled_at.is_(None)) | (CollectorQueueItem.scheduled_at <= datetime.now(timezone.utc)),
        ).order_by(CollectorQueueItem.priority.desc(), CollectorQueueItem.created_at).limit(batch_size)
        r = await self.session.execute(stmt)
        items = list(r.scalars().all())

        processed: list[CollectorQueueItem] = []
        for item in items:
            try:
                await self._process_queue_item(item)
                processed.append(item)
            except Exception as exc:
                self._log.error("queue_item_failed", item_id=item.id, error=str(exc))
                item.retry_count += 1
                item.last_error = str(exc)
                if item.retry_count >= item.max_retries:
                    item.status = "failed"
                else:
                    item.status = "pending"
                    delay = 2 ** item.retry_count
                    item.scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                await self.session.flush()
        return processed

    async def _process_queue_item(self, item: CollectorQueueItem) -> None:
        item.status = "processing"
        item.started_at = datetime.now(timezone.utc)
        await self.session.flush()

        if item.task_type == "incremental_sync":
            await self.orchestrator.incremental_sync(item.source_id, item.symbol)
        elif item.task_type == "historical_sync":
            payload = json.loads(item.payload_json) if item.payload_json else {}
            start = date.fromisoformat(payload["start"]) if "start" in payload else date.today() - timedelta(days=365)
            end = date.fromisoformat(payload["end"]) if "end" in payload else None
            await self.orchestrator.historical_sync(item.source_id, item.symbol, start, end)
        else:
            raise ValueError(f"Unknown task type: {item.task_type}")

        item.status = "completed"
        item.completed_at = datetime.now(timezone.utc)
        await self.session.flush()

    # ============================================================
    # QUEUE MANAGEMENT
    # ============================================================

    async def get_queue_stats(self) -> dict[str, int]:
        r = await self.session.execute(
            select(
                CollectorQueueItem.status,
                func.count(CollectorQueueItem.id),
            ).group_by(CollectorQueueItem.status)
        )
        stats: dict[str, int] = {}
        for status, count in r.all():
            stats[status] = count
        return stats

    async def list_queue_items(
        self, status: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[CollectorQueueItem]:
        stmt = select(CollectorQueueItem).order_by(
            CollectorQueueItem.priority.desc(), CollectorQueueItem.created_at.desc()
        )
        if status:
            stmt = stmt.where(CollectorQueueItem.status == status)
        stmt = stmt.offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def retry_failed_items(self) -> int:
        r = await self.session.execute(
            select(CollectorQueueItem).where(
                CollectorQueueItem.status == "failed",
                CollectorQueueItem.retry_count < CollectorQueueItem.max_retries,
            )
        )
        items = list(r.scalars().all())
        for item in items:
            item.status = "pending"
            item.last_error = None
        await self.session.flush()
        return len(items)

    async def clear_completed_items(self, older_than_days: int = 7) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        r = await self.session.execute(
            delete(CollectorQueueItem).where(
                CollectorQueueItem.status == "completed",
                CollectorQueueItem.completed_at <= cutoff,
            )
        )
        await self.session.flush()
        return r.rowcount

    # ============================================================
    # LIVE STREAMING
    # ============================================================

    async def start_live_stream(
        self, source_name: str, symbols: list[str]
    ) -> LiveStreamAdapter:
        if source_name in self._live_streams:
            raise ValueError(f"Live stream already active for source: {source_name}")

        adapter = MockLiveStreamAdapter(source_name)
        await adapter.connect(symbols)
        self._live_streams[source_name] = adapter
        self._log.info("live_stream_started", source=source_name, symbols=symbols)
        return adapter

    async def stop_live_stream(self, source_name: str) -> None:
        adapter = self._live_streams.pop(source_name, None)
        if adapter:
            await adapter.disconnect()

    async def consume_live_ticks(
        self, source_name: str, max_ticks: int = 10
    ) -> list[dict[str, Any]]:
        adapter = self._live_streams.get(source_name)
        if not adapter or not adapter.is_connected():
            raise ValueError(f"Live stream not active: {source_name}")
        ticks: list[dict[str, Any]] = []
        for _ in range(max_ticks):
            tick = await adapter.next_tick()
            if tick:
                ticks.append(tick)
        return ticks

    def get_active_streams(self) -> list[str]:
        return list(self._live_streams.keys())

    # ============================================================
    # VALIDATION
    # ============================================================

    async def validate_record(
        self, source_id: int, record: dict[str, Any]
    ) -> DataValidationResult:
        outcome = self.validator.validate(record)
        symbol = record.get("symbol", "")
        trade_date = record["trade_date"] if isinstance(record["trade_date"], date) \
            else date.fromisoformat(str(record["trade_date"]))

        result = DataValidationResult(
            source_id=source_id,
            symbol=symbol,
            trade_date=trade_date,
            status="passed" if outcome.passed else "failed",
            checks_passed=outcome.checks_passed,
            checks_failed=outcome.checks_failed,
            errors_json=json.dumps(outcome.errors) if outcome.errors else None,
            open=record.get("open"),
            high=record.get("high"),
            low=record.get("low"),
            close=record.get("close"),
            volume=record.get("volume"),
        )
        self.session.add(result)
        await self.session.flush()
        await self.session.refresh(result)
        return result

    async def get_validation_stats(self) -> dict[str, Any]:
        r = await self.session.execute(
            select(
                DataValidationResult.status,
                func.count(DataValidationResult.id),
            ).group_by(DataValidationResult.status)
        )
        stats: dict[str, int] = {}
        for status, count in r.all():
            stats[status] = count
        r2 = await self.session.execute(
            select(func.coalesce(func.sum(DataValidationResult.checks_failed), 0))
        )
        total_failed = r2.scalar() or 0
        r3 = await self.session.execute(
            select(func.coalesce(func.sum(DataValidationResult.checks_passed), 0))
        )
        total_passed = r3.scalar() or 0
        return {
            "by_status": stats,
            "total_checks_passed": total_passed,
            "total_checks_failed": total_failed,
            "pass_rate": round(total_passed / (total_passed + total_failed), 4)
            if (total_passed + total_failed) > 0 else 1.0,
        }

    # ============================================================
    # AUDIT LOGS
    # ============================================================

    async def get_sync_runs(
        self, source_id: int | None = None, symbol: str | None = None,
        sync_type: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[SyncRun]:
        stmt = select(SyncRun).order_by(SyncRun.started_at.desc())
        if source_id is not None:
            stmt = stmt.where(SyncRun.source_id == source_id)
        if symbol:
            stmt = stmt.where(SyncRun.symbol == symbol.upper())
        if sync_type:
            stmt = stmt.where(SyncRun.sync_type == sync_type)
        stmt = stmt.offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_audit_logs(
        self, sync_run_id: int | None = None, event_type: str | None = None,
        severity: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[SyncAuditLog]:
        stmt = select(SyncAuditLog).order_by(SyncAuditLog.created_at.desc())
        if sync_run_id is not None:
            stmt = stmt.where(SyncAuditLog.sync_run_id == sync_run_id)
        if event_type:
            stmt = stmt.where(SyncAuditLog.event_type == event_type)
        if severity:
            stmt = stmt.where(SyncAuditLog.severity == severity)
        stmt = stmt.offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_sync_stats(self) -> dict[str, Any]:
        r = await self.session.execute(
            select(
                SyncRun.sync_type,
                SyncRun.status,
                func.count(SyncRun.id),
            ).group_by(SyncRun.sync_type, SyncRun.status)
        )
        rows = r.all()
        stats: dict[str, dict[str, int]] = {}
        for sync_type, status, count in rows:
            if sync_type not in stats:
                stats[sync_type] = {}
            stats[sync_type][status] = count
        r2 = await self.session.execute(
            select(
                func.coalesce(func.sum(SyncRun.inserted), 0),
                func.coalesce(func.sum(SyncRun.updated), 0),
                func.coalesce(func.sum(SyncRun.skipped), 0),
                func.coalesce(func.sum(SyncRun.errors), 0),
            )
        )
        total_inserted, total_updated, total_skipped, total_errors = r2.one()
        return {
            "by_type_and_status": stats,
            "total_inserted": total_inserted,
            "total_updated": total_updated,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
        }

    # ============================================================
    # CHECKSUM OPERATIONS
    # ============================================================

    async def compute_checksum(
        self, symbol: str, trade_date: date, data_type: str = "daily_price"
    ) -> DataChecksum:
        return await self.checksum.compute(symbol, trade_date, data_type)

    async def verify_checksum(
        self, symbol: str, trade_date: date, data_type: str = "daily_price"
    ) -> bool:
        return await self.checksum.verify(symbol, trade_date, data_type)

    async def verify_checksum_batch(
        self, symbol: str, start: date, end: date, data_type: str = "daily_price"
    ) -> dict[str, Any]:
        return await self.checksum.verify_batch(symbol, start, end, data_type)

    # ============================================================
    # INTERNAL
    # ============================================================

    async def _audit(self, event_type: str, message: str, source_id: int | None = None) -> None:
        source_name = "system"
        if source_id:
            src = await self.get_source(source_id)
            if src:
                source_name = src.name
        log_entry = SyncAuditLog(
            sync_run_id=None,
            event_type=event_type,
            severity="info",
            message=message,
            source=source_name,
        )
        self.session.add(log_entry)
        await self.session.flush()