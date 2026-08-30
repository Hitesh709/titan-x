from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from titan_x.infrastructure.market_data_providers import MarketDataPoint, MarketDataProvider

IST = ZoneInfo("Asia/Kolkata")


class JugaadNSEProvider(MarketDataProvider):
    """Read-only NSE market-data adapter backed by jugaad-data."""

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
    def _as_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=IST)
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 100_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        text = str(value or "").strip()
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=IST)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)
        except ValueError as exc:
            raise ValueError(f"Unsupported NSE timestamp: {value!r}") from exc

    @classmethod
    def _iso_timestamp(cls, value: Any) -> str:
        return cls._as_datetime(value).astimezone(timezone.utc).isoformat()

    @staticmethod
    def _timestamp_date(value: Any) -> date:
        return JugaadNSEProvider._as_datetime(value).astimezone(IST).date()

    async def get_quote(self, symbol: str) -> dict:
        symbol = symbol.strip().upper()
        raw = await asyncio.to_thread(self._client().stock_quote, symbol)
        price_info = raw.get("priceInfo") or {}
        trade_info = raw.get("tradeInfo") or {}
        last_price = self._number(price_info.get("lastPrice"))
        if last_price is None or last_price <= 0:
            raise ValueError(f"No valid NSE LTP for {symbol}")
        timestamp_value = raw.get("lastUpdateTime")
        if not timestamp_value:
            raise ValueError(f"NSE did not provide a market timestamp for {symbol}")
        return {
            "symbol": symbol,
            "last_price": last_price,
            "change": self._number(price_info.get("change")),
            "change_percent": self._number(price_info.get("pChange")),
            "prev_close": self._number(price_info.get("previousClose")),
            "day_high": self._number((price_info.get("intraDayHighLow") or {}).get("max")),
            "day_low": self._number((price_info.get("intraDayHighLow") or {}).get("min")),
            "volume": self._number(trade_info.get("totalTradedVolume")),
            "vwap": self._number(price_info.get("vwap")),
            "timestamp": self._iso_timestamp(timestamp_value),
            "exchange": "NSE",
            "currency": "INR",
            "source": "jugaad-data/NSE",
        }

    @classmethod
    def _parse_chart_rows(cls, raw: dict, symbol: str) -> list[dict[str, Any]]:
        rows = raw.get("grapthData") or raw.get("graphData") or raw.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("values") or []
        if not isinstance(rows, list):
            return []
        parsed: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                ts = row.get("timestamp", row.get("time", row.get("date", row.get("x"))))
                close = cls._number(row.get("close", row.get("ltp", row.get("value", row.get("y")))))
                open_ = cls._number(row.get("open")) or close
                high = cls._number(row.get("high")) or close
                low = cls._number(row.get("low")) or close
                volume = cls._number(row.get("volume")) or 0
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                ts = row[0]
                if len(row) >= 5:
                    open_ = cls._number(row[1]); high = cls._number(row[2]); low = cls._number(row[3]); close = cls._number(row[4]); volume = cls._number(row[5]) if len(row) >= 6 else 0
                else:
                    close = cls._number(row[1]); open_ = high = low = close; volume = 0
            else:
                continue
            if close is None or close <= 0 or ts in (None, ""):
                continue
            try:
                timestamp = cls._as_datetime(ts).astimezone(timezone.utc)
            except ValueError:
                continue
            parsed.append({"time": timestamp.isoformat(), "open": float(open_ or close), "high": float(high or close), "low": float(low or close), "close": float(close), "volume": int(volume or 0), "symbol": symbol.upper()})
        return parsed

    @classmethod
    def _aggregate_candles(cls, rows: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
        if minutes <= 0:
            return rows
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            ts = datetime.fromisoformat(row["time"])
            bucket = ts.replace(minute=(ts.minute // minutes) * minutes, second=0, microsecond=0)
            key = bucket.isoformat()
            current = buckets.get(key)
            if current is None:
                buckets[key] = {"time": key, "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"], "volume": row["volume"]}
            else:
                current["high"] = max(current["high"], row["high"]); current["low"] = min(current["low"], row["low"]); current["close"] = row["close"]; current["volume"] += row["volume"]
        return list(sorted(buckets.values(), key=lambda x: x["time"]))

    async def get_candles(self, symbol: str, interval: str = "5m", period: str = "5d") -> list[dict[str, Any]]:
        symbol = symbol.strip().upper()
        interval = {"1h": "60m", "1w": "1wk", "1m": "1mo"}.get(interval.lower(), interval.lower())
        if interval not in {"5m", "15m", "30m", "60m", "1d", "1wk", "1mo"}:
            raise ValueError(f"Unsupported candle interval: {interval}")
        if interval in {"5m", "15m", "30m", "60m"}:
            raw = await asyncio.to_thread(self._client().symbol_chart_data, symbol, "EQ", "1D")
            return self._aggregate_candles(self._parse_chart_rows(raw or {}, symbol), int(interval[:-1]))
        from datetime import timedelta
        from jugaad_data.nse import stock_raw
        if period == "1mo": from_date = date.today().replace(day=1)
        elif period in {"1y", "max"}: from_date = date.today() - timedelta(days=365)
        elif period == "6mo": from_date = date.today() - timedelta(days=183)
        elif period == "3mo": from_date = date.today() - timedelta(days=92)
        elif period == "5d": from_date = date.today() - timedelta(days=5)
        else: from_date = date.today()
        raw_rows = await asyncio.to_thread(stock_raw, symbol, from_date, date.today(), "EQ")
        candles: list[dict[str, Any]] = []
        for row in raw_rows or []:
            try:
                candles.append({"time": self._as_datetime(row.get("CH_TIMESTAMP") or row.get("DATE")).astimezone(timezone.utc).isoformat(), "open": float(row.get("CH_OPENING_PRICE") or 0), "high": float(row.get("CH_TRADE_HIGH_PRICE") or 0), "low": float(row.get("CH_TRADE_LOW_PRICE") or 0), "close": float(row.get("CH_CLOSING_PRICE") or 0), "volume": int(float(row.get("CH_TOT_TRADED_QTY") or 0))})
            except (TypeError, ValueError):
                continue
        return [c for c in candles if c["close"] > 0]

    async def get_historical_prices(self, symbol: str, interval: str = "5m", start: date | None = None, end: date | None = None, synthetic_ok: bool = False) -> list[MarketDataPoint]:
        symbol = symbol.strip().upper()
        if interval in {"1m", "5m", "15m", "30m", "1h", "60m"}:
            raw = await asyncio.to_thread(self._client().symbol_chart_data, symbol, "EQ", "1D")
            rows = self._parse_chart_rows(raw or {}, symbol)
            result = [MarketDataPoint(symbol=symbol, trade_date=self._timestamp_date(p["time"]), open=p["open"], high=p["high"], low=p["low"], close=p["close"], volume=p["volume"]) for p in rows]
        else:
            from jugaad_data.nse import stock_raw
            raw_rows = await asyncio.to_thread(stock_raw, symbol, start or date.today(), end or date.today(), "EQ")
            result = []
            for row in raw_rows or []:
                try:
                    result.append(MarketDataPoint(symbol=symbol, trade_date=self._timestamp_date(row.get("CH_TIMESTAMP") or row.get("DATE")), open=float(row.get("CH_OPENING_PRICE") or 0), high=float(row.get("CH_TRADE_HIGH_PRICE") or 0), low=float(row.get("CH_TRADE_LOW_PRICE") or 0), close=float(row.get("CH_CLOSING_PRICE") or 0), volume=int(float(row.get("CH_TOT_TRADED_QTY") or 0)))
                except (TypeError, ValueError):
                    continue
        lower, upper = start or date.min, end or date.max
        return [p for p in result if p.close > 0 and lower <= p.trade_date <= upper]

    async def get_company_profile(self, symbol: str) -> dict:
        try:
            raw = await asyncio.to_thread(self._client().symbol_meta, symbol.strip().upper())
        except Exception:
            raw = {}
        return {"symbol": symbol.strip().upper(), "name": raw.get("companyName") if isinstance(raw, dict) else None, "sector": None, "industry": raw.get("industry") if isinstance(raw, dict) else None, "market_cap": None, "exchange": "NSE", "currency": "INR"}

    async def close(self) -> None:
        if self._live is not None and hasattr(self._live, "s"):
            try:
                await asyncio.to_thread(self._live.s.close)
            except Exception:
                pass
        self._live = None
