from datetime import UTC, datetime

import structlog

from titan_x.jobs.base import ScheduledJob

logger = structlog.get_logger(__name__)


class MarketOpenJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("market_open", "market", max_retries=3, retry_delay=60)

    async def _run(self, payload: dict) -> dict:
        logger.info("market_opening")
        return {"market": "open", "timestamp": datetime.now(UTC).isoformat()}


class MarketCloseJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("market_close", "market", max_retries=3, retry_delay=60)

    async def _run(self, payload: dict) -> dict:
        logger.info("market_closing")
        return {"market": "closed", "timestamp": datetime.now(UTC).isoformat()}


class MarketDataIngestionJob(ScheduledJob):
    def __init__(self, session_factory=None) -> None:
        super().__init__("market_data_ingestion", "market", max_retries=5, retry_delay=120)
        self._session_factory = session_factory

    async def _run(self, payload: dict) -> dict:
        symbol: str | None = payload.get("symbol")
        symbols: list[str] = payload.get("symbols") or ([symbol] if symbol else [])
        logger.info("ingesting_market_data", symbols=symbols, count=len(symbols))
        if not symbols:
            symbols = ["RELIANCE", "TCS", "HDFCBANK"]

        factory = self._session_factory
        if factory is None:
            from titan_x.core.config import get_settings
            from titan_x.db.session import create_engine, create_session_factory

            factory = create_session_factory(create_engine(get_settings()))

        from titan_x.services.market_data_service import run_market_data_ingestion

        result = await run_market_data_ingestion(
            factory,
            symbol=symbol,
            symbols=symbols,
            max_symbols=payload.get("max_symbols", 100),
            lookback_days=payload.get("lookback_days", 365),
        )
        return {
            "symbols_requested": result.get("symbols_requested", len(symbols)),
            "symbols_ingested": result.get("symbols_ok", 0),
            "symbols": symbols,
            "symbols_ok": result.get("symbols_ok", 0),
            "symbols_failed": result.get("symbols_failed", 0),
            "inserted_total": result.get("inserted_total", 0),
            "errors": result.get("errors", []),
        }


class ProcessDelayedTradesJob(ScheduledJob):
    def __init__(self) -> None:
        super().__init__("process_delayed_trades", "market", max_retries=3, retry_delay=30)

    async def _run(self, payload: dict) -> dict:
        batch_size: int = payload.get("batch_size", 100)
        logger.info("processing_delayed_trades", batch_size=batch_size)
        return {"processed": 0, "batch_size": batch_size}
