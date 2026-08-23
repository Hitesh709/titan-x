from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from titan_x.services.market_data_normalization_service import MarketDataNormalizationService


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
    """Provider-neutral live quote engine with canonical validation."""

    def __init__(
        self,
        fetch_quote: QuoteFetcher,
        *,
        stale_after_seconds: float = 15.0,
        normalizer: MarketDataNormalizationService | None = None,
    ):
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self._fetch_quote = fetch_quote
        self.stale_after_seconds = stale_after_seconds
        self._normalizer = normalizer or MarketDataNormalizationService()
        self._latest: dict[str, LiveQuote] = {}
        self._sequence: dict[str, int] = {}
        self._subscribers: set[QuoteSubscriber] = set()
        self._stop_event = asyncio.Event()

    def normalize(self, symbol: str, payload: dict[str, Any], sequence: int) -> LiveQuote:
        canonical = self._normalizer.normalize(symbol, payload)
        return LiveQuote(
            symbol=canonical["symbol"],
            last_price=canonical["last_price"],
            change=canonical["change"],
            change_percent=canonical["change_percent"],
            volume=canonical["volume"],
            exchange=canonical["exchange"],
            currency=canonical["currency"],
            source=canonical["source"],
            timestamp=canonical["timestamp"],
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
        except (TypeError, ValueError):
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
