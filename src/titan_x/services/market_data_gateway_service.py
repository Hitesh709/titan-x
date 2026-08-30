from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis

from titan_x.services.market_data_normalization_service import MarketDataNormalizationService

QuoteFetcher = Callable[[str], Awaitable[dict[str, Any]]]


class MarketDataGateway:
    """Single market-data boundary for Titan-X.

    Provider adapters feed this service; consumers never need to know which
    upstream provider is active. Invalid or stale quotes are never exposed as
    tradeable prices.
    """

    def __init__(
        self,
        fetch_quote: QuoteFetcher,
        *,
        provider_name: str,
        redis: Redis | None = None,
        stale_after_seconds: float = 15.0,
    ) -> None:
        self.fetch_quote = fetch_quote
        self.provider_name = provider_name
        self.redis = redis
        self.stale_after_seconds = stale_after_seconds
        self.normalizer = MarketDataNormalizationService()
        self.latest: dict[str, dict[str, Any]] = {}
        self.candles: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._last_timestamp: dict[str, datetime] = {}

    async def ingest(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.strip().upper()
        payload = await self.fetch_quote(symbol)
        quote = self.normalizer.normalize(symbol, payload)
        self.normalizer.validate(quote)
        timestamp = datetime.fromisoformat(quote["timestamp"])
        previous = self._last_timestamp.get(symbol)
        if previous is not None and timestamp <= previous:
            raise ValueError(f"out-of-order market tick for {symbol}")
        self._last_timestamp[symbol] = timestamp
        quote["provider"] = self.provider_name
        quote["status"] = "valid"
        self.latest[symbol] = quote
        self._update_candle(symbol, quote, timestamp)
        if self.redis is not None:
            await self.redis.set(
                f"titanx:market:quote:{symbol}",
                json.dumps(quote),
                ex=max(1, int(self.stale_after_seconds * 2)),
            )
        return quote

    def _update_candle(self, symbol: str, quote: dict[str, Any], timestamp: datetime) -> None:
        bucket = timestamp.replace(second=0, microsecond=0)
        key = bucket.isoformat()
        existing = self.candles[symbol].get(key)
        price = float(quote["last_price"])
        volume = float(quote.get("volume") or 0)
        if existing is None:
            self.candles[symbol][key] = {
                "timestamp": key,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
            }
        else:
            existing["high"] = max(existing["high"], price)
            existing["low"] = min(existing["low"], price)
            existing["close"] = price
            existing["volume"] = max(existing["volume"], volume)
        cutoff = bucket - timedelta(minutes=24 * 60)
        self.candles[symbol] = {
            k: v for k, v in self.candles[symbol].items()
            if datetime.fromisoformat(k) >= cutoff
        }

    async def quote(self, symbol: str, *, refresh: bool = True) -> dict[str, Any]:
        symbol = symbol.strip().upper()
        if refresh:
            try:
                return await self.ingest(symbol)
            except Exception:
                pass
        quote = self.latest.get(symbol)
        if quote is None and self.redis is not None:
            cached = await self.redis.get(f"titanx:market:quote:{symbol}")
            if cached:
                quote = json.loads(cached)
        if quote is None:
            raise ValueError(f"no market price available for {symbol}")
        if self.is_stale(quote):
            raise ValueError(f"market price is stale for {symbol}")
        return quote

    def is_stale(self, quote: dict[str, Any]) -> bool:
        try:
            ts = datetime.fromisoformat(str(quote["timestamp"]))
            return (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds() > self.stale_after_seconds
        except (KeyError, TypeError, ValueError):
            return True

    def get_candles(self, symbol: str, interval_minutes: int = 1, limit: int = 100) -> list[dict[str, Any]]:
        if interval_minutes not in {1, 5, 15, 30, 60}:
            raise ValueError("interval_minutes must be one of 1, 5, 15, 30, 60")
        symbol = symbol.strip().upper()
        rows = sorted(self.candles.get(symbol, {}).values(), key=lambda x: x["timestamp"])
        if interval_minutes == 1:
            return rows[-limit:]
        aggregated: dict[str, dict[str, Any]] = {}
        for row in rows:
            ts = datetime.fromisoformat(row["timestamp"])
            minute = (ts.minute // interval_minutes) * interval_minutes
            bucket = ts.replace(minute=minute, second=0, microsecond=0).isoformat()
            current = aggregated.get(bucket)
            if current is None:
                aggregated[bucket] = {**row, "timestamp": bucket}
            else:
                current["high"] = max(current["high"], row["high"])
                current["low"] = min(current["low"], row["low"])
                current["close"] = row["close"]
                current["volume"] += row["volume"]
        return list(aggregated.values())[-limit:]

    def health(self, symbols: list[str]) -> dict[str, Any]:
        normalized = [s.strip().upper() for s in symbols if s.strip()]
        stale = [s for s in normalized if s not in self.latest or self.is_stale(self.latest[s])]
        return {
            "status": "healthy" if not stale else "degraded",
            "provider": self.provider_name,
            "symbols": len(normalized),
            "valid": len(normalized) - len(stale),
            "stale_or_missing": stale,
            "tradeable": not stale,
        }

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()
