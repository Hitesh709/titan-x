"""Upstox V3 market-data adapter for Titan-X.

This module is read-only: it never places, modifies, or cancels broker orders.
It supports the long-lived Upstox Analytics Token for market-data access and
uses MarketDataStreamerV3 for live WebSocket updates.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from titan_x.infrastructure.market_data_providers import MarketDataPoint, MarketDataProvider


class UpstoxProvider(MarketDataProvider):
    """Read-only Upstox market-data provider.

    Required environment variable:
        UPSTOX_ANALYTICS_TOKEN

    Optional:
        UPSTOX_API_BASE_URL (defaults to https://api.upstox.com/v2)
        UPSTOX_WS_MODE (ltpc/full; defaults to ltpc)
    """

    BASE_URL = "https://api.upstox.com/v2"

    def __init__(self, api_key: str | None = None):
        self.token = api_key or os.getenv("UPSTOX_ANALYTICS_TOKEN", "")
        self.base_url = os.getenv("UPSTOX_API_BASE_URL", self.BASE_URL).rstrip("/")
        self.ws_mode = os.getenv("UPSTOX_WS_MODE", "ltpc")
        self._client = httpx.AsyncClient(
            timeout=20.0,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
        )

    @staticmethod
    def _instrument_key(symbol: str) -> str:
        """Accept an Upstox instrument key or a bare NSE symbol.

        Bare symbols require instrument-token resolution before WebSocket
        subscription. Keep that resolution outside this adapter so the token
        is never guessed.
        """
        symbol = symbol.strip().upper()
        if "|" in symbol:
            return symbol
        raise ValueError(
            f"Upstox instrument key required for live streaming: {symbol}. "
            """Use the Upstox instrument master/search service to resolve it."""
        )

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("UPSTOX_ANALYTICS_TOKEN is not configured")
        response = await self._client.get(f"{self.base_url}/{path.lstrip('/')}", params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in (None, "success"):
            raise RuntimeError(f"Upstox API error: {payload}")
        return payload

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Return the latest quote using the Upstox market quote endpoint."""
        instrument = self._instrument_key(symbol)
        payload = await self._request("market-quote/quotes", {"instrument_key": instrument})
        data = payload.get("data") or {}
        quote = next(iter(data.values()), {}) if data else {}
        return {
            "symbol": symbol,
            "instrument_key": instrument,
            "last_price": quote.get("last_price") or quote.get("ltp"),
            "prev_close": quote.get("prev_close_price") or quote.get("cp"),
            "open": quote.get("ohlc", {}).get("open") if isinstance(quote.get("ohlc"), dict) else None,
            "high": quote.get("ohlc", {}).get("high") if isinstance(quote.get("ohlc"), dict) else None,
            "low": quote.get("ohlc", {}).get("low") if isinstance(quote.get("ohlc"), dict) else None,
            "volume": quote.get("volume") or quote.get("volume_traded"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "upstox",
        }

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        """Fetch historical candles through Upstox's historical candle API."""
        instrument = self._instrument_key(symbol)
        if interval in {"1m", "I1", "1min"}:
            interval_value = "1minute"
        elif interval in {"30m", "I30", "30min"}:
            interval_value = "30minute"
        elif interval in {"1d", "D"}:
            interval_value = "day"
        else:
            raise ValueError(f"Unsupported Upstox historical interval: {interval}")

        end_date = end or date.today()
        start_date = start or (end_date - timedelta(days=365))
        payload = await self._request(
            f"historical-candle/{instrument}/{interval_value}/{end_date.isoformat()}/{start_date.isoformat()}"
        )
        candles = (payload.get("data") or {}).get("candles") or []
        points: list[MarketDataPoint] = []
        for candle in candles:
            if len(candle) < 6:
                continue
            ts, o, h, l, c, volume = candle[:6]
            if isinstance(ts, str):
                trade_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            else:
                trade_date = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
            points.append(
                MarketDataPoint(
                    symbol=symbol.upper(),
                    trade_date=trade_date,
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=int(volume or 0),
                )
            )
        return points

    async def get_company_profile(self, symbol: str) -> dict[str, Any]:
        quote = await self.get_quote(symbol)
        return {
            "symbol": symbol.upper(),
            "name": None,
            "sector": None,
            "industry": None,
            "market_cap": None,
            "exchange": "NSE",
            "currency": "INR",
            "source": "upstox",
        }

    async def close(self) -> None:
        await self._client.aclose()


class UpstoxLiveStreamer:
    """Thin adapter around the official MarketDataStreamerV3 SDK.

    Callers provide an async-safe callback. The callback receives normalized
    dictionaries containing instrument_key, LTP, exchange timestamp and close.
    """

    def __init__(self, token: str | None = None, mode: str | None = None):
        self.token = token or os.getenv("UPSTOX_ANALYTICS_TOKEN", "")
        self.mode = mode or os.getenv("UPSTOX_WS_MODE", "ltpc")
        self._streamer = None

    def start(
        self,
        instrument_keys: list[str],
        on_tick: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        if not self.token:
            raise RuntimeError("UPSTOX_ANALYTICS_TOKEN is not configured")
        if not instrument_keys:
            raise ValueError("At least one Upstox instrument key is required")

        try:
            import upstox_client
        except ImportError as exc:
            raise RuntimeError(
                "Install upstox-python-sdk before starting the Upstox WebSocket"
            ) from exc

        configuration = upstox_client.Configuration()
        configuration.access_token = self.token
        api_client = upstox_client.ApiClient(configuration)
        self._streamer = upstox_client.MarketDataStreamerV3(
            api_client, instrument_keys, self.mode
        )

        def handle_message(message: dict[str, Any]) -> None:
            current_ts = message.get("currentTs")
            feeds = message.get("feeds") or {}
            for instrument_key, feed in feeds.items():
                ltpc = feed.get("ltpc") or feed.get("firstLevelWithGreeks", {}).get("ltpc") or feed.get("fullFeed", {}).get("marketFF", {}).get("ltpc") or {}
                ltp = ltpc.get("ltp")
                if ltp is None:
                    continue
                tick = {
                    "instrument_key": instrument_key,
                    "ltp": float(ltp),
                    "close": ltpc.get("cp"),
                    "last_trade_time": ltpc.get("ltt"),
                    "last_trade_quantity": ltpc.get("ltq"),
                    "received_ts": current_ts,
                    "source": "upstox",
                }
                result = on_tick(tick)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)

        self._streamer.on("message", handle_message)
        self._streamer.auto_reconnect(True, 5, 0)
        self._streamer.connect()

    def stop(self) -> None:
        if self._streamer is not None:
            self._streamer.disconnect()
            self._streamer = None
