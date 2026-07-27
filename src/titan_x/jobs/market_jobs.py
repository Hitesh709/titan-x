from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.jobs.base import ScheduledJob

logger = structlog.get_logger(__name__)


class MarketOpenJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("market_open", "market", max_retries=3, retry_delay=60)

    async def _run(self, payload: dict) -> dict:
        logger.info("market_opening")
        return {"market": "open", "timestamp": datetime.now(timezone.utc).isoformat()}


class MarketCloseJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("market_close", "market", max_retries=3, retry_delay=60)

    async def _run(self, payload: dict) -> dict:
        logger.info("market_closing")
        return {"market": "closed", "timestamp": datetime.now(timezone.utc).isoformat()}


class MarketDataIngestionJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("market_data_ingestion", "market", max_retries=5, retry_delay=120)

    async def _run(self, payload: dict) -> dict:
        symbols: list[str] = payload.get("symbols", ["AAPL", "GOOGL", "MSFT"])
        logger.info("ingesting_market_data", symbols=symbols, count=len(symbols))
        return {"symbols_ingested": len(symbols), "symbols": symbols}


class ProcessDelayedTradesJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("process_delayed_trades", "market", max_retries=3, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        batch_size: int = payload.get("batch_size", 100)
        logger.info("processing_delayed_trades", batch_size=batch_size)
        return {"processed": 0, "batch_size": batch_size}
