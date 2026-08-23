from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SendMessage = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class LiveMarketConnection:
    send: SendMessage
    symbols: tuple[str, ...]
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LiveMarketWebSocketService:
    """Fan-out manager for live quote streams.

    The service deliberately keeps transport state separate from the quote
    provider. A connection can subscribe to a bounded symbol set and receives
    normalized quote messages until disconnected.
    """

    def __init__(self, poller: Callable[[list[str]], Awaitable[dict[str, Any]]], interval: float = 1.0) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        self._poller = poller
        self._interval = interval
        self._connections: dict[int, LiveMarketConnection] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def connect(self, send: SendMessage, symbols: list[str]) -> int:
        normalized = tuple(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not normalized or len(normalized) > 100:
            raise ValueError("WebSocket subscription must contain 1-100 symbols")
        async with self._lock:
            connection_id = self._next_id
            self._next_id += 1
            self._connections[connection_id] = LiveMarketConnection(send=send, symbols=normalized)
            return connection_id

    async def disconnect(self, connection_id: int) -> None:
        async with self._lock:
            self._connections.pop(connection_id, None)

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            connections = list(self._connections.values())
        symbols = sorted({symbol for connection in connections for symbol in connection.symbols})
        return {"connections": len(connections), "symbols": symbols, "interval_seconds": self._interval}

    async def broadcast_once(self) -> int:
        async with self._lock:
            connections = list(self._connections.items())
        if not connections:
            return 0
        all_symbols = sorted({symbol for _, connection in connections for symbol in connection.symbols})
        try:
            quotes = await self._poller(all_symbols)
        except Exception:
            return 0

        sent = 0
        for connection_id, connection in connections:
            payload = {
                "type": "market.quote",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "quotes": {symbol: quotes[symbol] for symbol in connection.symbols if symbol in quotes},
            }
            if not payload["quotes"]:
                continue
            try:
                await connection.send(payload)
                sent += 1
            except Exception:
                await self.disconnect(connection_id)
        return sent

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.broadcast_once()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        async with self._lock:
            self._connections.clear()
