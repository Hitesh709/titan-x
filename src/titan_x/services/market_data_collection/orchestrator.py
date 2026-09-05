"""Sync orchestrator that drives historical/incremental syncs and persistence."""
import json
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.market_data_collector import (
    DataSource,
    DataValidationResult,
    SyncAuditLog,
    SyncRun,
)
from titan_x.models.price import DailyPrice

from .adapters import MockSourceAdapter, SourceAdapter
from .checksum import ChecksumService
from .models import SyncResult
from .validation import DataValidator

logger = structlog.get_logger(__name__)


class SyncOrchestrator:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.validator = DataValidator()
        self.checksum = ChecksumService(session)
        self._log = logger.bind(service="sync_orchestrator")

    async def incremental_sync(
        self, source_id: int, symbol: str
    ) -> SyncRun:
        source = await self._get_source(source_id)
        adapter = self._get_adapter(source)

        last = await self._get_last_sync_date(source_id, symbol)
        since = self._incremental_start(last)

        sync_run = SyncRun(
            source_id=source_id,
            sync_type="incremental",
            status="running",
            started_at=datetime.now(timezone.utc),
            symbol=symbol,
            date_from=since,
            date_to=date.today(),
        )
        self.session.add(sync_run)
        await self.session.flush()
        await self.session.refresh(sync_run)

        start_time = time.monotonic()
        result = SyncResult()

        try:
            records = await adapter.fetch_incremental(symbol, since)
            result = await self._process_records(
                sync_run.id, source_id, symbol, records, is_incremental=True
            )
        except Exception as exc:
            result.errors = 1
            result.error_message = str(exc)
            self._log.error("incremental_sync_failed", symbol=symbol, error=str(exc))

        elapsed = time.monotonic() - start_time
        result.duration_ms = int(elapsed * 1000)

        sync_run.status = "completed" if result.error_message is None else "failed"
        sync_run.completed_at = datetime.now(timezone.utc)
        sync_run.total_records = result.total
        sync_run.inserted = result.inserted
        sync_run.updated = result.updated
        sync_run.skipped = result.skipped
        sync_run.errors = result.errors
        sync_run.error_message = result.error_message
        sync_run.duration_ms = result.duration_ms
        await self.session.flush()

        await self._log_event(
            sync_run.id, source.name,
            "incremental_completed" if result.error_message is None else "incremental_failed",
            "info" if result.error_message is None else "error",
            f"Incremental sync for {symbol}: {result.inserted} inserted, {result.updated} updated, {result.skipped} skipped in {result.duration_ms}ms",
            {"inserted": result.inserted, "updated": result.updated, "skipped": result.skipped,
             "total": result.total, "errors": result.errors, "duration_ms": result.duration_ms},
        )

        if result.error_message is None:
            source.last_sync_at = datetime.now(timezone.utc)
            source.error_count = 0
        else:
            source.error_count = source.error_count + 1
        await self.session.flush()

        return sync_run

    @staticmethod
    def _incremental_start(last: date | None) -> date:
        """Return a safe inclusive start date, including the prior business day on weekends."""
        if last is None:
            return date.today() - timedelta(days=7)
        since = last
        today = date.today()
        if since >= today and today.weekday() >= 5:
            while since.weekday() >= 5:
                since -= timedelta(days=1)
        return since

    async def historical_sync(
        self, source_id: int, symbol: str, start: date, end: date | None = None
    ) -> SyncRun:
        source = await self._get_source(source_id)
        adapter = self._get_adapter(source)
        if end is None:
            end = date.today()

        sync_run = SyncRun(
            source_id=source_id,
            sync_type="historical",
            status="running",
            started_at=datetime.now(timezone.utc),
            symbol=symbol,
            date_from=start,
            date_to=end,
        )
        self.session.add(sync_run)
        await self.session.flush()
        await self.session.refresh(sync_run)

        start_time = time.monotonic()
        result = SyncResult()

        try:
            records = await adapter.fetch_historical(symbol, start, end)
            result = await self._process_records(
                sync_run.id, source_id, symbol, records, is_incremental=False
            )
        except Exception as exc:
            result.errors = 1
            result.error_message = str(exc)
            self._log.error("historical_sync_failed", symbol=symbol, error=str(exc))

        elapsed = time.monotonic() - start_time
        result.duration_ms = int(elapsed * 1000)

        sync_run.status = "completed" if result.error_message is None else "failed"
        sync_run.completed_at = datetime.now(timezone.utc)
        sync_run.total_records = result.total
        sync_run.inserted = result.inserted
        sync_run.updated = result.updated
        sync_run.skipped = result.skipped
        sync_run.errors = result.errors
        sync_run.error_message = result.error_message
        sync_run.duration_ms = result.duration_ms
        await self.session.flush()

        await self._log_event(
            sync_run.id, source.name,
            "historical_completed" if result.error_message is None else "historical_failed",
            "info" if result.error_message is None else "error",
            f"Historical sync for {symbol} ({start} to {end}): {result.inserted} inserted in {result.duration_ms}ms",
            {"inserted": result.inserted, "updated": result.updated, "skipped": result.skipped,
             "total": result.total, "errors": result.errors, "duration_ms": result.duration_ms},
        )

        if result.error_message is None:
            source.last_sync_at = datetime.now(timezone.utc)
            source.error_count = 0
        else:
            source.error_count = source.error_count + 1
        await self.session.flush()

        return sync_run

    async def _process_records(
        self, sync_run_id: int, source_id: int, symbol: str,
        records: list[dict[str, Any]], is_incremental: bool,
    ) -> SyncResult:
        result = SyncResult(total=len(records))

        for rec in records:
            outcome = self.validator.validate(rec)
            val_result = DataValidationResult(
                source_id=source_id,
                symbol=symbol,
                trade_date=rec["trade_date"] if isinstance(rec["trade_date"], date)
                else date.fromisoformat(str(rec["trade_date"])),
                status="passed" if outcome.passed else "failed",
                checks_passed=outcome.checks_passed,
                checks_failed=outcome.checks_failed,
                errors_json=json.dumps(outcome.errors) if outcome.errors else None,
                open=rec.get("open"),
                high=rec.get("high"),
                low=rec.get("low"),
                close=rec.get("close"),
                volume=rec.get("volume"),
            )
            self.session.add(val_result)

            if not outcome.passed:
                result.errors += 1
                continue

            await self._upsert_price(symbol, rec, is_incremental, result)
            await self.checksum.compute(symbol, rec["trade_date"] if isinstance(rec["trade_date"], date)
                                        else date.fromisoformat(str(rec["trade_date"])))

        return result

    async def _upsert_price(
        self, symbol: str, rec: dict[str, Any],
        is_incremental: bool, result: SyncResult,
    ) -> None:
        trade_date = rec["trade_date"] if isinstance(rec["trade_date"], date) \
            else date.fromisoformat(str(rec["trade_date"]))

        stmt = select(DailyPrice).where(
            DailyPrice.symbol == symbol, DailyPrice.trade_date == trade_date
        )
        r = await self.session.execute(stmt)
        existing = r.scalar_one_or_none()

        if existing:
            if is_incremental:
                existing.open = rec["open"]
                existing.high = rec["high"]
                existing.low = rec["low"]
                existing.close = rec["close"]
                existing.volume = rec["volume"]
                result.updated += 1
            else:
                result.skipped += 1
        else:
            dp = DailyPrice(
                symbol=symbol,
                trade_date=trade_date,
                open=rec["open"],
                high=rec["high"],
                low=rec["low"],
                close=rec["close"],
                volume=rec["volume"],
            )
            self.session.add(dp)
            result.inserted += 1

    async def _get_source(self, source_id: int) -> DataSource:
        r = await self.session.execute(
            select(DataSource).where(DataSource.id == source_id)
        )
        source = r.scalar_one_or_none()
        if not source:
            raise ValueError(f"DataSource {source_id} not found")
        return source

    def _get_adapter(self, source: DataSource) -> SourceAdapter:
        if source.provider_type == "mock":
            return MockSourceAdapter(source)
        raise ValueError(f"Unsupported provider type: {source.provider_type}")

    async def _get_last_sync_date(self, source_id: int, symbol: str) -> date | None:
        r = await self.session.execute(
            select(SyncRun).where(
                SyncRun.source_id == source_id,
                SyncRun.symbol == symbol,
                SyncRun.status == "completed",
            ).order_by(SyncRun.started_at.desc()).limit(1)
        )
        last = r.scalar_one_or_none()
        if last and last.date_to:
            return last.date_to
        return None

    async def _log_event(
        self, sync_run_id: int, source: str, event_type: str,
        severity: str, message: str, details: dict | None = None,
    ) -> None:
        log_entry = SyncAuditLog(
            sync_run_id=sync_run_id,
            event_type=event_type,
            severity=severity,
            message=message,
            details_json=json.dumps(details) if details else None,
            source=source,
        )
        self.session.add(log_entry)
        await self.session.flush()
