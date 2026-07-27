"""Scheduled job for market scanning."""
import structlog

from titan_x.jobs.base import ScheduledJob
from titan_x.services.market_scanner_service import MarketScannerService

logger = structlog.get_logger(__name__)


class MarketScanJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__(
            "market_scan", "daily",
            max_retries=2, retry_delay=60,
        )

    async def _run(self, payload: dict) -> dict:
        session = payload.get("session")
        if session is None:
            return {"status": "failed", "error": "Missing session"}

        service = MarketScannerService(session)
        results = await service.scan_all()

        logger.info("market_scan_completed", symbols_scanned=len(results))
        return {
            "status": "success",
            "symbols_scanned": len(results),
        }
