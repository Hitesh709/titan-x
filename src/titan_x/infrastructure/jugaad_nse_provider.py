from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from titan_x.infrastructure.market_data_providers import MarketDataPoint, MarketDataProvider


IST = ZoneInfo("Asia/Kolkata")


class JugaadNSEProvider(MarketDataProvider):
    """Read-only NSE market-data adapter backed by jugaad-data.

    This adapter is the single NSE provider for the current private/demo build.
    It never creates a price and has no broker/order capability.
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
    def _as_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=IST)
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 100_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        text = str(value or "").strip()
        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ):
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

    @staticmethod
    def _parse_chart_rows(raw: dict, symbol: str) -> list[dict[str, Any]]:
        rows = raw.get("grapthData") or raw.get("graphData") or raw.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("values") or []
        if not isinstance(rows, list):
            return []

        parsed: list[dict[str, Any]] = []
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
                if len(row) >= 5:
                    open_ = JugaadNSEProvider._number(row[1])
                    high = JugaadNSEProvider._number(row[2])
                    low = JugaadNSEProvider._number(row[3])
                    close = JugaadNSEProvider._number(row[4])
                    volume = JugaadNSEProvider._number(row[5]) if len(row) >= 6 else 0
                else:
                    close = JugaadNSEProvider._number(row[1])
                    open_ = high = low = close
                    volume = 0
            else:
                continue
            if close is None or close <= 0 or ts in (None, ""):
                continue
            try:
                timestamp = JugaadNSEProvider._as_datetime(ts).astimezone(timezone.utc)
            except ValueError:
                continue
            parsed.append({
                "time": timestamp.isoformat(),
                "open": float(open_ or close),
                "high": float(high or close),
                "low": float(low or close),
                "close": float(close),
                "volume": int(volume or 0),
                "symbol": symbol.upper(),
            })
        return parsed

    @classmethod
    def _aggregate_candles(cls, rows: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
        if minutes <= 0:
            return rows
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            ts = datetime.fromisoformat(row["time"])
            bucket_minute = (ts.minute // minutes) * minutes
            bucket = ts.replace(minute=bucket_minute, second=0, microsecond=0)
            key = bucket.isoformat()
            current = buckets.get(key)
            if current is None:
                buckets[key] = {
                    "time": key,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
            else:
                current["high"] = max(current["high"], row["high"])
                current["low"] = min(current["low"], row["low"])
                current["close"] = row["close"]
                current["volume"] += row["volume"]
        return list(sorted(buckets.values(), key=lambda x: x["time"]))

    async def get_candles(self, symbol: str, interval: str = "5m", period: str = "5d") -> list[dict[str, Any]]:
        """Return real NSE candles where the current NSE chart endpoint supports them.

        Intraday chart data comes from NSE's getSymbolChartData endpoint. Daily
        history uses jugaad-data's NSEHistory stock_raw endpoint.
        """
        symbol = symbol.strip().upper()
        interval = interval.lower()
        if interval == "1h":
            interval = "60m"
        if interval == "1w":
            interval = "1wk"
        if interval == "1m":
            interval = "1mo"
        allowed = {"5m", "15m", "30m", "60m", "1d", "1wk", "1mo"}
        if interval not in allowed:
            raise ValueError(f"Unsupported candle interval: {interval}")

        if interval in {"5m", "15m", "30m", "60m"}:
            days = "1D" if period in {"1d", "5d", "1mo", "3mo", "max"} else "1D"
            raw = await asyncio.to_thread(self._client().symbol_chart_data, symbol, "EQ", days)
            rows = self._parse_chart_rows(raw or {}, symbol)
            minutes = int(interval[:-1])
            return self._aggregate_candles(rows, minutes)

        from_date = date.today()
        if period == "1d":
            from_date = date.today()
        elif period == "5d":
            from_date = date.today()
        elif period == "1mo":
            from_date = date.today().replace(day=1)
        else:
            from datetime import timedelta

            from_date = date.today() - timedelta(days=365 if period in {"1y", "max"} else 30)
        try:
            from jugaad_data.nse import stock_raw

            raw_rows = await asyncio.to_thread(stock_raw, symbol, from_date, date.today(), "EQ")
        except Exception as exc:
            raise ValueError(f"NSE historical data unavailable for {symbol}: {exc}") from exc
        candles: list[dict[str, Any]] = []
        for row in raw_rows or []:
            try:
                timestamp = row.get("CH_TIMESTAMP") or row.get("DATE")
                candles.append({
                    "time": self._as_datetime(timestamp).astimezone(timezone.utc).isoformat(),
                    "open": float(row.get("CH_OPENING_PRICE") or 0),
                    "high": float(row.get("CH_TRADE_HIGH_PRICE") or 0),
                    "low": float(row.get("CH_TRADE_LOW_PRICE") or 0),
                    "close": float(row.get("CH_CLOSING_PRICE") or 0),
                    "volume": int(float(row.get("CH_TOT_TRADED_QTY") or 0)),
                })
            except (TypeError, ValueError):
                continue
        return [c for c in candles if c["close"] > 0]

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "5m",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        if interval in {"1m", "5m", "15m", "30m", "1h", "60m"}:
            raw = await asyncio.to_thread(self._client().symbol_chart_data, symbol.strip().upper(), "EQ", "1D")
            points = self._parse_chart_rows(raw or {}, symbol)
            result = [
                MarketDataPoint(
                    symbol=symbol.upper(),
                    trade_date=self._timestamp_date(p["time"]),
                    open=p["open"],
                    high=p["high"],
                    low=p["low"],
                    close=p["close"],
                    volume=p["volume"],
                )
                for p in points
            ]
        else:
            from jugaad_data.nse import stock_raw

            raw_rows = await asyncio.to_thread(stock_raw, symbol.strip().upper(), start or date.today(), end or date.today(), "EQ")
            result = []
            for row in raw_rows or []:
                try:
                    result.append(MarketDataPoint(
                        symbol=symbol.upper(),
                        trade_date=self._timestamp_date(row.get("CH_TIMESTAMP") or row.get("DATE")),
                        open=float(row.get("CH_OPENING_PRICE") or 0),
                        high=float(row.get("CH_TRADE_HIGH_PRICE") or 0),
                        low=float(row.get("CH_TRADE_LOW_PRICE") or 0),
                        close=float(row.get("CH_CLOSING_PRICE") or 0),
                        volume=int(float(row.get("CH_TOT_TRADED_QTY") or 0)),
                    ))
                except (TypeError, ValueError):
                    continue
        if start or end:
            lower = start or date.min
            upper = end or date.max
            result = [p for p in result if lower <= p.trade_date <= upper]
        return [p for p in result if p.close > 0]

    async def get_company_profile(self, symbol: str) -> dict:
        try:
            raw = await asyncio.to_thread(self._client().symbol_meta, symbol.strip().upper())
        except Exception:
            raw = {}
        return {
            "symbol": symbol.strip().upper(),
            "name": raw.get("companyName") if isinstance(raw, dict) else None,
            "sector": None,
            "industry": raw.get("industry") if isinstance(raw, dict) else None,
            "market_cap": None,
            "exchange": "NSE",
            "currency": "INR",
        }

    async def close(self) -> None:
        self._live = None
