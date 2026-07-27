import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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

logger = structlog.get_logger(__name__)


# ============================================================
# DATA CLASSES
# ============================================================


@dataclass
class SyncResult:
    total: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_message: str | None = None
    duration_ms: int | None = None


@dataclass
class ValidationOutcome:
    passed: bool = False
    checks_passed: int = 0
    checks_failed: int = 0
    errors: list[str] = field(default_factory=list)


# ============================================================
# SOURCE ADAPTER
# ============================================================


class SourceAdapter(ABC):
    @abstractmethod
    async def fetch_historical(
        self, symbol: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def fetch_incremental(
        self, symbol: str, since: date
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def fetch_live(self, symbol: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class MockSourceAdapter(SourceAdapter):
    def __init__(self, source: DataSource):
        self.source = source
        self._log = logger.bind(source=source.name)

    async def fetch_historical(
        self, symbol: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        self._log.info("fetch_historical", symbol=symbol, start=start, end=end)
        points: list[dict[str, Any]] = []
        current = start
        base_price = 100.0
        i = 0
        while current <= end:
            if current.weekday() < 5:
                price = base_price + i * 0.5 + (hash(f"{symbol}_{i}") % 20 - 10)
                points.append({
                    "symbol": symbol,
                    "trade_date": current,
                    "open": price,
                    "high": price + 2.0,
                    "low": price - 2.0,
                    "close": price + 0.5,
                    "volume": 1_000_000 + (hash(f"{symbol}_v{i}") % 500_000),
                })
                i += 1
            current += timedelta(days=1)
        return points

    async def fetch_incremental(
        self, symbol: str, since: date
    ) -> list[dict[str, Any]]:
        return await self.fetch_historical(symbol, since, date.today())

    async def fetch_live(self, symbol: str) -> dict[str, Any] | None:
        return None

    async def health_check(self) -> bool:
        return True


# ============================================================
# LIVE STREAM ADAPTER
# ============================================================


class LiveStreamAdapter(ABC):
    @abstractmethod
    async def connect(self, symbols: list[str]) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def next_tick(self) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...


class MockLiveStreamAdapter(LiveStreamAdapter):
    def __init__(self, source_name: str = "mock"):
        self.source_name = source_name
        self._symbols: list[str] = []
        self._connected = False
        self._tick_count = 0
        self._log = logger.bind(source=source_name)

    async def connect(self, symbols: list[str]) -> None:
        self._symbols = symbols
        self._connected = True
        self._tick_count = 0
        self._log.info("live_stream_connected", symbols=symbols)

    async def disconnect(self) -> None:
        self._connected = False
        self._log.info("live_stream_disconnected")

    async def next_tick(self) -> dict[str, Any] | None:
        if not self._connected or not self._symbols:
            return None
        self._tick_count += 1
        await asyncio.sleep(0.01)
        sym = self._symbols[self._tick_count % len(self._symbols)]
        base = 100.0 + (hash(f"{sym}_{self._tick_count}") % 10 - 5)
        return {
            "symbol": sym,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "last_price": base,
            "open": base - 0.5,
            "high": base + 1.0,
            "low": base - 1.0,
            "volume": 100_000 + (hash(f"v_{self._tick_count}") % 10_000),
            "tick_id": self._tick_count,
        }

    def is_connected(self) -> bool:
        return self._connected


# ============================================================
# DATA VALIDATOR
# ============================================================


class DataValidator:
    VALIDATION_RULES = [
        "positive_price",
        "high_low_consistency",
        "open_close_range",
        "positive_volume",
        "no_nan_values",
        "no_infinite_values",
        "date_not_future",
        "ohlc_consistency",
    ]

    def validate(self, record: dict[str, Any]) -> ValidationOutcome:
        outcome = ValidationOutcome()
        errors: list[str] = []

        if self._check_positive_price(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("price_not_positive")

        if self._check_high_low_consistency(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("high_low_inconsistent")

        if self._check_open_close_range(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("open_close_out_of_range")

        if self._check_positive_volume(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("volume_not_positive")

        if self._check_no_nan(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("nan_value_found")

        if self._check_no_infinite(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("infinite_value_found")

        if self._check_date_not_future(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("date_in_future")

        if self._check_ohlc_consistency(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("ohlc_consistency_failed")

        outcome.passed = outcome.checks_failed == 0
        outcome.errors = errors
        return outcome

    @staticmethod
    def _check_positive_price(record: dict[str, Any]) -> bool:
        return all(
            record.get(k, 0) is not None and record.get(k, 0) > 0
            for k in ("open", "high", "low", "close")
        )

    @staticmethod
    def _check_high_low_consistency(record: dict[str, Any]) -> bool:
        high = record.get("high")
        low = record.get("low")
        if high is None or low is None:
            return False
        return high >= low

    @staticmethod
    def _check_open_close_range(record: dict[str, Any]) -> bool:
        high = record.get("high")
        low = record.get("low")
        opn = record.get("open")
        close = record.get("close")
        if any(v is None for v in (high, low, opn, close)):
            return False
        return low <= opn <= high and low <= close <= high

    @staticmethod
    def _check_positive_volume(record: dict[str, Any]) -> bool:
        vol = record.get("volume")
        return vol is not None and vol > 0

    @staticmethod
    def _check_no_nan(record: dict[str, Any]) -> bool:
        import math
        for k in ("open", "high", "low", "close", "volume"):
            v = record.get(k)
            if v is not None and isinstance(v, float) and math.isnan(v):
                return False
        return True

    @staticmethod
    def _check_no_infinite(record: dict[str, Any]) -> bool:
        import math
        for k in ("open", "high", "low", "close", "volume"):
            v = record.get(k)
            if v is not None and isinstance(v, float) and math.isinf(v):
                return False
        return True

    @staticmethod
    def _check_date_not_future(record: dict[str, Any]) -> bool:
        d = record.get("trade_date")
        if d is None:
            return False
        if isinstance(d, str):
            from datetime import date as dt_date
            d = dt_date.fromisoformat(d)
        return d <= date.today()

    @staticmethod
    def _check_ohlc_consistency(record: dict[str, Any]) -> bool:
        close = record.get("close")
        opn = record.get("open")
        if close is None or opn is None:
            return False
        return abs(close - opn) <= abs(record.get("high", 0) - record.get("low", 0)) * 2


# ============================================================
# CHECKSUM SERVICE
# ============================================================


class ChecksumService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._log = logger.bind(service="checksum")

    async def compute(
        self, symbol: str, trade_date: date, data_type: str = "daily_price"
    ) -> DataChecksum:
        stmt = select(DailyPrice).where(
            DailyPrice.symbol == symbol, DailyPrice.trade_date == trade_date
        )
        r = await self.session.execute(stmt)
        rows = r.scalars().all()

        raw = json.dumps(
            [{"o": p.open, "h": p.high, "l": p.low, "c": p.close, "v": p.volume} for p in rows],
            sort_keys=True, default=str,
        )
        sha = hashlib.sha256(raw.encode()).hexdigest()

        existing = await self.session.execute(
            select(DataChecksum).where(
                DataChecksum.symbol == symbol,
                DataChecksum.trade_date == trade_date,
                DataChecksum.data_type == data_type,
            )
        )
        chk = existing.scalar_one_or_none()
        if chk:
            chk.checksum_sha256 = sha
            chk.row_count = len(rows)
            chk.verified_at = None
            chk.is_verified = False
        else:
            chk = DataChecksum(
                symbol=symbol,
                trade_date=trade_date,
                data_type=data_type,
                checksum_sha256=sha,
                row_count=len(rows),
            )
            self.session.add(chk)
        await self.session.flush()
        await self.session.refresh(chk)
        return chk

    async def verify(
        self, symbol: str, trade_date: date, data_type: str = "daily_price"
    ) -> bool:
        stmt = select(DataChecksum).where(
            DataChecksum.symbol == symbol,
            DataChecksum.trade_date == trade_date,
            DataChecksum.data_type == data_type,
        ).order_by(DataChecksum.created_at.desc()).limit(1)
        r = await self.session.execute(stmt)
        stored = r.scalar_one_or_none()
        if not stored:
            return False

        fresh = await self.compute(symbol, trade_date, data_type)
        matches = fresh.checksum_sha256 == stored.checksum_sha256

        stored.is_verified = matches
        stored.verified_at = datetime.now(timezone.utc)
        await self.session.flush()

        if not matches:
            self._log.warning("checksum_mismatch", symbol=symbol, trade_date=trade_date.isoformat())
        return matches

    async def verify_batch(
        self, symbol: str, start: date, end: date, data_type: str = "daily_price"
    ) -> dict[str, Any]:
        results = {"verified": 0, "mismatched": 0, "missing": 0, "total": 0}
        current = start
        while current <= end:
            if current.weekday() < 5:
                results["total"] += 1
                ok = await self.verify(symbol, current, data_type)
                if ok:
                    results["verified"] += 1
                else:
                    stmt = select(DataChecksum).where(
                        DataChecksum.symbol == symbol,
                        DataChecksum.trade_date == current,
                        DataChecksum.data_type == data_type,
                    )
                    r = await self.session.execute(stmt)
                    exists = r.scalar_one_or_none()
                    if exists:
                        results["mismatched"] += 1
                    else:
                        results["missing"] += 1
            current += timedelta(days=1)
        return results


# ============================================================
# SYNC ORCHESTRATOR
# ============================================================


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
        since = last or (date.today() - timedelta(days=7))

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


# ============================================================
# MARKET DATA COLLECTOR SERVICE
# ============================================================


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
            stmt = stmt.where(DataSource.enabled == True, DataSource.status == "active")
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
