from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from titan_x.infrastructure.market_data_providers import MarketDataPoint, MarketDataProvider


class JugaadNSEProvider(MarketDataProvider):
    """Read-only NSE market-data adapter backed by jugaad-data.

    This adapter is intentionally isolated from the rest of the provider
    registry so it can be removed cleanly when Titan-X moves to a licensed
    market-data feed. No broker account, API key, or order capability is used.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._live: Any | None = None

    def _client(self) -> Any:
        if self._live is None:
            from jugaad_data.nse import NSELive

            self._live = NSELive()
        return self._live

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _timestamp(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 100_000_000_000 else value
            return datetime.fromtimestamp(seconds).date()
        text = str(value or "")
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return date.today()

    @staticmethod
    def _iso_timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)):
            seconds = value / 1000 if value > 100_000_000_000 else value
            dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        else:
            text = str(value or "").strip()
            dt = None
            for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            if dt is None:
                return datetime.now(timezone.utc).isoformat()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    async def get_quote(self, symbol: str) -> dict:
        raw = await asyncio.to_thread(self._client().stock_quote, symbol.strip().upper())
        price_info = raw.get("priceInfo") or {}
        trade_info = raw.get("tradeInfo") or {}
        last_price = self._number(price_info.get("lastPrice"))
        if last_price is None or last_price <= 0:
            raise ValueError(f"No valid NSE LTP for {symbol}")
        return {
            "symbol": symbol.strip().upper(),
            "last_price": last_price,
            "change": self._number(price_info.get("change")),
            "change_percent": self._number(price_info.get("pChange")),
            "prev_close": self._number(price_info.get("previousClose")),
            "day_high": self._number((price_info.get("intraDayHighLow") or {}).get("max")),
            "day_low": self._number((price_info.get("intraDayHighLow") or {}).get("min")),
            "volume": self._number(trade_info.get("totalTradedVolume")),
            "vwap": self._number(price_info.get("vwap")),
            "timestamp": self._iso_timestamp(raw.get("lastUpdateTime")),
            "exchange": "NSE",
            "source": "jugaad-data/NSE",
        }

    @staticmethod
    def _parse_chart(raw: dict, symbol: str) -> list[MarketDataPoint]:
        rows = raw.get("grapthData") or raw.get("graphData") or raw.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("values") or []
        if not isinstance(rows, list):
            return []

        points: list[MarketDataPoint] = []
        for row in rows:
            if isinstance(row, dict):
                ts = row.get("timestamp", row.get("time", row.get("date")))
                close = JugaadNSEProvider._number(row.get("close", row.get("ltp", row.get("value"))))
                open_ = JugaadNSEProvider._number(row.get("open")) or close
                high = JugaadNSEProvider._number(row.get("high")) or close
                low = JugaadNSEProvider._number(row.get("low")) or close
                volume = JugaadNSEProvider._number(row.get("volume")) or 0
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                ts = row[0]
                close = JugaadNSEProvider._number(row[4] if len(row) >= 5 else row[1])
                open_ = JugaadNSEProvider._number(row[1]) or close
                high = JugaadNSEProvider._number(row[2]) or close
                low = JugaadNSEProvider._number(row[3]) or close
                volume = JugaadNSEProvider._number(row[5]) if len(row) >= 6 else 0
            else:
                continue
            if close is None or close <= 0:
                continue
            points.append(
                MarketDataPoint(
                    symbol=symbol.upper(),
                    trade_date=JugaadNSEProvider._timestamp(ts),
                    open=open_ or close,
                    high=high or close,
                    low=low or close,
                    close=close,
                    volume=int(volume or 0),
                )
            )
        return points

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "5m",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        days = "1D" if interval in {"1m", "5m", "15m", "30m", "1h"} else "1M"
        raw = await asyncio.to_thread(self._client().symbol_chart_data, symbol.strip().upper(), "EQ", days)
        points = self._parse_chart(raw or {}, symbol)
        if start or end:
            lower = start or date.min
            upper = end or date.max
            points = [p for p in points if lower <= p.trade_date <= upper]
        return points

    async def get_company_profile(self, symbol: str) -> dict:
        try:
            raw = await asyncio.to_thread(self._client().symbol_meta, symbol.strip().upper())
        except Exception:
            raw = {}
        return {
            "symbol": symbol.strip().upper(),
            "name": raw.get("companyName") if isinstance(raw, dict) else None,
            "sector": None,
            "industry": None,
            "market_cap": None,
            "exchange": "NSE",
        }

    async def close(self) -> None:
        self._live = None
