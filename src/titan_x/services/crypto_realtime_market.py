"""Low-latency Binance market stream for the crypto paper bot.

The stream is the hot path: no REST request is made for each decision.
Historical REST candles remain a fallback/warm-up source.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any

import httpx
import structlog
import websockets

log = structlog.get_logger(__name__)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT")
TIMEFRAMES = ("5m", "15m", "30m")
STREAMS = [f"{s.lower()}@miniTicker" for s in SYMBOLS]
STREAMS += [f"{s.lower()}@kline_{tf}" for s in SYMBOLS for tf in TIMEFRAMES]
URL = "wss://stream.binance.com:9443/stream?streams=" + "/".join(STREAMS)

class CryptoRealtimeMarket:
    def __init__(self) -> None:
        self.prices: dict[str, float] = {}
        self.ticks: dict[str, int] = {}
        self.candles: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
        self.connected = False
        self.messages = 0
        self.last_event_ms = 0
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._changed_symbols: set[str] = set()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            await self._warmup()
            self._task = asyncio.create_task(self._run(), name="crypto-realtime-market")

    async def _warmup(self) -> None:
        async def load(symbol: str, tf: str) -> None:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get(
                        "https://api.binance.com/api/v3/klines",
                        params={"symbol": symbol, "interval": tf, "limit": 180},
                    )
                    response.raise_for_status()
                    rows = response.json()
                self.candles[symbol][tf] = [
                    {
                        "open": float(x[1]),
                        "high": float(x[2]),
                        "low": float(x[3]),
                        "close": float(x[4]),
                        "volume": float(x[5]),
                        "closed": True,
                        "open_time": float(x[0]),
                    }
                    for x in rows
                ][-220:]
                if rows:
                    self.prices[symbol] = float(rows[-1][4])
            except Exception as exc:
                log.warning(
                    "crypto_realtime_warmup_failed",
                    symbol=symbol,
                    timeframe=tf,
                    error=str(exc),
                )

        await asyncio.gather(
            *(load(symbol, tf) for symbol in SYMBOLS for tf in TIMEFRAMES)
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def snapshot(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "price": self.prices.get(symbol),
            "event_ms": self.ticks.get(symbol),
            "candles": {tf: list(self.candles[symbol][tf]) for tf in TIMEFRAMES},
            "connected": self.connected,
        }

    def consume_changed_symbols(self) -> set[str]:
        changed = set(self._changed_symbols)
        self._changed_symbols.clear()
        return changed

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    URL,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=2,
                    max_queue=4096,
                ) as ws:
                    self.connected = True
                    backoff = 1.0
                    log.info("crypto_realtime_connected")
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        self._handle(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("crypto_realtime_disconnected", error=str(exc))
            finally:
                self.connected = False
            if not self._stop.is_set():
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    def _handle(self, raw: str | bytes) -> None:
        try:
            envelope = json.loads(raw)
            data = envelope.get("data", envelope)
            event = data.get("e")
            symbol = data.get("s")
            if not symbol:
                return
            self.messages += 1
            self.last_event_ms = int(data.get("E") or time.time() * 1000)

            if event == "24hrMiniTicker":
                self.prices[symbol] = float(data["c"])
                self.ticks[symbol] = self.last_event_ms
                self._changed_symbols.add(symbol)
                return

            if event == "kline":
                k = data.get("k", {})
                tf = k.get("i")
                if tf not in TIMEFRAMES:
                    return
                candle = {
                    "open": float(k["o"]),
                    "high": float(k["h"]),
                    "low": float(k["l"]),
                    "close": float(k["c"]),
                    "volume": float(k["v"]),
                    "closed": bool(k.get("x")),
                    "open_time": float(k["t"]),
                }
                series = self.candles[symbol][tf]
                if series and series[-1]["open_time"] == candle["open_time"]:
                    series[-1] = candle
                else:
                    series.append(candle)
                    if len(series) > 220:
                        del series[:-220]
                self.prices[symbol] = candle["close"]
                self.ticks[symbol] = self.last_event_ms
                self._changed_symbols.add(symbol)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return

MARKET = CryptoRealtimeMarket()
