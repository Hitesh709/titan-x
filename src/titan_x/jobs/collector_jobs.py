from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from titan_x.jobs.base import BaseJob, ScheduledJob
from titan_x.models.company import Company
from titan_x.services.market_data_collector_service import MarketDataCollectorService

logger = structlog.get_logger(__name__)


class HistoricalSyncJob(BaseJob):
    def __init__(self, session_factory, max_retries: int = 3, retry_delay: int = 60):
        super().__init__("historical_sync", max_retries, retry_delay)
        self.session_factory = session_factory

    async def _run(self, payload: dict) -> dict:
        symbol = payload.get("symbol", "")
        source_id = payload.get("source_id")
        start = payload.get("start")
        end = payload.get("end")

        async with self.session_factory() as session:
            svc = MarketDataCollectorService(session)
            sources = await svc.list_sources(enabled_only=True)
            if source_id:
                sources = [s for s in sources if s.id == source_id]
                if not sources:
                    return {"symbol": symbol, "error": "Source not found"}

            results = []
            for src in sources:
                run = await svc.run_historical_sync(
                    src.id, symbol,
                    date.fromisoformat(start) if isinstance(start, str) else start,
                    date.fromisoformat(end) if isinstance(end, str) else end,
                )
                results.append({
                    "source_id": src.id,
                    "source_name": src.name,
                    "sync_run_id": run.id,
                    "status": run.status,
                    "inserted": run.inserted,
                })

            return {"symbol": symbol, "results": results}


class IncrementalSyncJob(BaseJob):
    def __init__(self, session_factory, max_retries: int = 3, retry_delay: int = 60):
        super().__init__("incremental_sync", max_retries, retry_delay)
        self.session_factory = session_factory

    async def _run(self, payload: dict) -> dict:
        symbol = payload.get("symbol", "")
        source_id = payload.get("source_id")

        async with self.session_factory() as session:
            svc = MarketDataCollectorService(session)
            sources = await svc.list_sources(enabled_only=True)
            if source_id:
                sources = [s for s in sources if s.id == source_id]

            results = []
            for src in sources:
                run = await svc.run_incremental_sync(src.id, symbol)
                results.append({
                    "source_id": src.id,
                    "source_name": src.name,
                    "sync_run_id": run.id,
                    "status": run.status,
                    "inserted": run.inserted,
                    "updated": run.updated,
                })

            return {"symbol": symbol, "results": results}


class SyncAllSymbolsJob(ScheduledJob):
    def __init__(self, session_factory, max_retries: int = 3, retry_delay: int = 60):
        super().__init__("sync_all_symbols", "daily", max_retries, retry_delay)
        self.session_factory = session_factory

    async def _run(self, payload: dict) -> dict:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Company.symbol).where(Company.status == "active")
            )
            symbols = [r[0] for r in result.all()]

            svc = MarketDataCollectorService(session)
            sources = await svc.list_sources(enabled_only=True)

            total_inserted = 0
            total_updated = 0
            total_errors = 0
            synced = 0

            for sym in symbols[:payload.get("max_symbols", 500)]:
                for src in sources:
                    try:
                        run = await svc.run_incremental_sync(src.id, sym)
                        total_inserted += run.inserted
                        total_updated += run.updated
                        synced += 1
                    except Exception as exc:
                        total_errors += 1
                        logger.error("sync_failed", symbol=sym, source=src.name, error=str(exc))

            return {
                "symbols_processed": len(symbols),
                "sync_operations": synced,
                "total_inserted": total_inserted,
                "total_updated": total_updated,
                "total_errors": total_errors,
            }


class ProcessCollectorQueueJob(BaseJob):
    def __init__(self, session_factory, max_retries: int = 3, retry_delay: int = 30):
        super().__init__("process_collector_queue", max_retries, retry_delay)
        self.session_factory = session_factory

    async def _run(self, payload: dict) -> dict:
        batch_size = payload.get("batch_size", 10)
        async with self.session_factory() as session:
            svc = MarketDataCollectorService(session)
            processed = await svc.process_queue(batch_size)
            return {"processed_count": len(processed)}


class VerifyDataIntegrityJob(ScheduledJob):
    def __init__(self, session_factory, max_retries: int = 2, retry_delay: int = 120):
        super().__init__("verify_data_integrity", "daily", max_retries, retry_delay)
        self.session_factory = session_factory

    async def _run(self, payload: dict) -> dict:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Company.symbol).where(Company.status == "active")
            )
            symbols = [r[0] for r in result.all()]

            svc = MarketDataCollectorService(session)
            today = date.today()
            yesterday = today - timedelta(days=1)

            total_verified = 0
            total_mismatched = 0
            total_missing = 0

            for sym in symbols[:payload.get("max_symbols", 100)]:
                batch = await svc.verify_checksum_batch(sym, yesterday, yesterday)
                total_verified += batch.get("verified", 0)
                total_mismatched += batch.get("mismatched", 0)
                total_missing += batch.get("missing", 0)

            return {
                "symbols_checked": len(symbols[:payload.get("max_symbols", 100)]),
                "verified": total_verified,
                "mismatched": total_mismatched,
                "missing": total_missing,
            }
