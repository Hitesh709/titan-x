"""Source and live-stream adapters for the market data collection pipeline."""
import asyncio
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog

from titan_x.models.market_data_collector import DataSource

logger = structlog.get_logger(__name__)


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