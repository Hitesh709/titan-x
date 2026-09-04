from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, time as dt_time, timezone

import httpx

YAHOO_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
)


class MarketDataPoint:
    def __init__(
        self,
        symbol: str,
        trade_date: date,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: int,
    ):
        self.symbol = symbol
        self.trade_date = trade_date
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class MarketDataProvider(ABC):
    @abstractmethod
    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]: ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict: ...

    @abstractmethod
    async def get_company_profile(self, symbol: str) -> dict: ...


class MockMarketDataProvider(MarketDataProvider):
    """Deterministic offline provider used by unit and integration tests."""

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        start = start or (date.today() - timedelta(days=30))
        end = end or date.today()
        if end < start:
            return []
        points: list[MarketDataPoint] = []
        cursor = start
        base = 100.0
        day = 0
        while cursor <= end:
            if cursor.weekday() < 5:
                close = base + day * 0.5
                points.append(
                    MarketDataPoint(
                        symbol=symbol.upper(),
                        trade_date=cursor,
                        open=close - 1.0,
                        high=close + 2.0,
                        low=close - 2.0,
                        close=close,
                        volume=100_000 + day * 1000,
                    )
                )
                day += 1
            cursor += timedelta(days=1)
        return points

    async def get_quote(self, symbol: str) -> dict:
        symbol = symbol.upper()
        return {
            "symbol": symbol,
            "last_price": 150.0,
            "prev_close": 148.0,
            "change": 2.0,
            "change_percent": 1.35135,
            "volume": 100_000,
            "day_high": 152.0,
            "day_low": 147.0,
            "currency": "INR",
            "name": f"{symbol} Corp",
            "exchange": "NSE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_company_profile(self, symbol: str) -> dict:
        symbol = symbol.upper()
        return {
            "symbol": symbol,
            "name": f"{symbol} Corp",
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 1_000_000_000.0,
            "exchange": "NSE",
            "currency": "INR",
        }

    async def close(self) -> None:
        return None


class YahooFinanceProvider(MarketDataProvider):
    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    _global_sem = asyncio.Semaphore(10)

    def __init__(self, api_key: str | None = None):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": YAHOO_USER_AGENT},
            timeout=20,
            follow_redirects=True,
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if "." in normalized or normalized.startswith("^"):
            return normalized
        return normalized + ".NS"

    async def _get(self, symbol: str, params: dict) -> dict:
        last: Exception | None = None
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                async with self._global_sem:
                    response = await self._client.get(
                        f"https://{host}/v8/finance/chart/{self._normalize_symbol(symbol)}",
                        params=params,
                    )
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last = exc
        raise last or RuntimeError("Yahoo request failed")

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        params = {"interval": interval}
        if start is not None:
            params["period1"] = int(
                datetime.combine(start, dt_time.min)
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
            params["period2"] = int(
                datetime.combine(end or date.today() + timedelta(days=1), dt_time.min)
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
        else:
            params["range"] = "5d" if interval in {"5m", "15m", "30m"} else "1y"

        data = await self._get(symbol, params)
        result = (data.get("chart") or {}).get("result")
        if not result:
            raise ValueError(f"No Yahoo data for {symbol}")

        chart = result[0]
        timestamps = chart.get("timestamp") or []
        quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
        output: list[MarketDataPoint] = []
        for index, timestamp in enumerate(timestamps):
            closes = quote.get("close", [])
            close = closes[index] if index < len(closes) else None
            if close is None:
                continue

            def value(key: str) -> float:
                values = quote.get(key, [])
                return float(values[index]) if index < len(values) and values[index] is not None else float(close)

            volumes = quote.get("volume", [])
            volume = int(volumes[index] or 0) if index < len(volumes) else 0
            output.append(
                MarketDataPoint(
                    symbol.upper(),
                    datetime.fromtimestamp(timestamp, timezone.utc).date(),
                    value("open"),
                    value("high"),
                    value("low"),
                    float(close),
                    volume,
                )
            )
        return output

    async def get_quote(self, symbol: str) -> dict:
        data = await self._get(symbol, {"range": "5d", "interval": "1d"})
        result = (data.get("chart") or {}).get("result")
        if not result:
            raise ValueError(f"No Yahoo quote for {symbol}")
        meta = result[0].get("meta") or {}
        return {
            "symbol": meta.get("symbol", self._normalize_symbol(symbol)),
            "last_price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose"),
            "change": None,
            "change_percent": None,
            "volume": meta.get("regularMarketVolume"),
            "day_high": meta.get("regularMarketDayHigh"),
            "day_low": meta.get("regularMarketDayLow"),
            "currency": meta.get("currency"),
            "name": meta.get("longName") or meta.get("shortName"),
            "exchange": meta.get("fullExchangeName"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_company_profile(self, symbol: str) -> dict:
        quote = await self.get_quote(symbol)
        normalized = self._normalize_symbol(symbol)
        return {
            "symbol": symbol.upper(),
            "name": quote.get("name") or symbol.upper(),
            "sector": None,
            "industry": None,
            "market_cap": None,
            "exchange": (
                "NSE"
                if normalized.endswith(".NS")
                else "BSE"
                if normalized.endswith(".BO")
                else quote.get("exchange")
            ),
            "currency": quote.get("currency") or "INR",
        }

    async def close(self) -> None:
        await self._client.aclose()


# Legacy provider names remain available for compatibility. They use Yahoo's
# live implementation; only the mock provider is synthetic.
NSEProvider = YahooFinanceProvider
StooqProvider = YahooFinanceProvider
AlphaVantageProvider = YahooFinanceProvider


def get_market_data_provider(
    provider_name: str = "yahoo", api_key: str | None = None
) -> MarketDataProvider:
    name = provider_name.lower().strip()
    if name == "mock":
        return MockMarketDataProvider()
    if name in {"yahoo", "nse", "stooq", "alphavantage"}:
        return YahooFinanceProvider(api_key)
    raise ValueError(f"Unsupported market data provider: {provider_name}")
