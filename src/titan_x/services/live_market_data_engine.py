from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class LiveQuote:
    symbol: str
    last_price: float
    change: float | None = None
    change_percent: float | None = None
    volume: int | float | None = None
    exchange: str | None = None
    currency: str | None = None
    source: str = "unknown"
    timestamp: str = ""
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


QuoteFetcher = Callable[[str], Awaitable[dict[str, Any]]]
QuoteSubscriber = Callable[[LiveQuote], Awaitable[None] | None]


class LiveMarketDataEngine:
    """Provider-neutral live quote engine.

    Responsibilities are deliberately limited to quote polling, normalization,
    freshness, deduplication and subscriber delivery. Broker/WebSocket transport
    belongs to the next Sprint 4 items.
    """

    def __init__(self, fetch_quote: QuoteFetcher, *, stale_after_seconds: float = 15.0):
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self._fetch_quote = fetch_quote
        self.stale_after_seconds = stale_after_seconds
        self._latest: dict[str, LiveQuote] = {}
        self._sequence: dict[str, int] = {}
        self._subscribers: set[QuoteSubscriber] = set()
        self._stop_event = asyncio.Event()

    @staticmethod
    def normalize(symbol: str, payload: dict[str, Any], sequence: int) -> LiveQuote:
        symbol = symbol.strip().upper()
        price = payload.get("last_price", payload.get("price", payload.get("ltp")))
        if not symbol:
            raise ValueError("symbol cannot be empty")
        if price is None:
            raise ValueError(f"missing last price for {symbol}")
        price = float(price)
        if price <= 0:
            raise ValueError(f"last price must be positive for {symbol}")
        raw_ts = payload.get("timestamp") or payload.get("ts")
        if isinstance(raw_ts, datetime):
            timestamp = raw_ts.astimezone(timezone.utc).isoformat()
        elif raw_ts:
            timestamp = str(raw_ts)
        else:
            timestamp = datetime.now(timezone.utc).isoformat()
        volume = payload.get("volume")
        return LiveQuote(
            symbol=symbol,
            last_price=price,
            change=float(payload["change"]) if payload.get("change") is not None else None,
            change_percent=(float(payload["change_percent"]) if payload.get("change_percent") is not None else None),
            volume=volume,
            exchange=payload.get("exchange"),
            currency=payload.get("currency", "INR"),
            source=str(payload.get("source", "live")),
            timestamp=timestamp,
            sequence=sequence,
        )

    def subscribe(self, callback: QuoteSubscriber) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: QuoteSubscriber) -> None:
        self._subscribers.discard(callback)

    def get_latest(self, symbol: str) -> LiveQuote | None:
        return self._latest.get(symbol.strip().upper())

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {symbol: quote.to_dict() for symbol, quote in self._latest.items()}

    def is_stale(self, symbol: str, now: float | None = None) -> bool:
        quote = self.get_latest(symbol)
        if quote is None:
            return True
        try:
            timestamp = datetime.fromisoformat(quote.timestamp.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        except ValueError:
            return True
        return age > self.stale_after_seconds

    async def poll_once(self, symbols: list[str]) -> dict[str, Any]:
        normalized_symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not normalized_symbols:
            return {"updated": 0, "failed": 0, "quotes": [], "errors": []}

        results = await asyncio.gather(
            *(self._fetch_one(symbol) for symbol in normalized_symbols),
            return_exceptions=True,
        )
        updated: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for symbol, result in zip(normalized_symbols, results):
            if isinstance(result, Exception):
                errors.append({"symbol": symbol, "error": str(result)})
            else:
                updated.append(result.to_dict())
        return {"updated": len(updated), "failed": len(errors), "quotes": updated, "errors": errors}

    async def _fetch_one(self, symbol: str) -> LiveQuote:
        payload = await self._fetch_quote(symbol)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid quote payload for {symbol}")
        sequence = self._sequence.get(symbol, 0) + 1
        quote = self.normalize(symbol, payload, sequence)
        self._sequence[symbol] = sequence
        self._latest[symbol] = quote
        await self._publish(quote)
        return quote

    async def _publish(self, quote: LiveQuote) -> None:
        for subscriber in tuple(self._subscribers):
            try:
                result = subscriber(quote)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # One consumer must never stop market-data ingestion for all others.
                continue

    async def run(self, symbols: list[str], interval_seconds: float = 2.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._stop_event.clear()
        while not self._stop_event.is_set():
            started = time.monotonic()
            await self.poll_once(symbols)
            elapsed = time.monotonic() - started
            try:
                await asyncio.wait_for(self._stop_event.wait(), max(0.0, interval_seconds - elapsed))
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop_event.set()

    def health(self, symbols: list[str]) -> dict[str, Any]:
        symbols = [s.strip().upper() for s in symbols if s.strip()]
        stale = [s for s in symbols if self.is_stale(s)]
        return {
            "status": "degraded" if stale else "healthy",
            "symbols": len(symbols),
            "received": len(symbols) - len(stale),
            "stale": stale,
            "tracked": len(self._latest),
        }
