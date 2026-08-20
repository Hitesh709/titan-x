import asyncio
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

import httpx

YAHOO_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
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
    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        start_date = start or date.today() - timedelta(days=365)
        end_date = end or date.today()
        points = []
        current = start_date
        base_price = 100.0
        i = 0
        while current <= end_date:
            if current.weekday() < 5:
                price = base_price + i * 0.5 + (hash(f"{symbol}_{i}") % 20 - 10)
                points.append(
                    MarketDataPoint(
                        symbol=symbol,
                        trade_date=current,
                        open=price,
                        high=price + 2,
                        low=price - 2,
                        close=price + 0.5,
                        volume=1_000_000 + (hash(f"{symbol}_v{i}") % 500_000),
                    )
                )
                i += 1
            current += timedelta(days=1)
        return points

    async def get_quote(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "last_price": 150.0,
            "change": 2.5,
            "change_percent": 1.67,
            "volume": 2_500_000,
            "timestamp": datetime.now().isoformat(),
        }

    async def get_company_profile(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "name": f"{symbol} Corp",
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 100_000_000_000,
            "exchange": "NSE",
        }


class AlphaVantageProvider(MarketDataProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        raise NotImplementedError("Alpha Vantage not configured")

    async def get_quote(self, symbol: str) -> dict:
        raise NotImplementedError("Alpha Vantage not configured")

    async def get_company_profile(self, symbol: str) -> dict:
        raise NotImplementedError("Alpha Vantage not configured")


class YahooFinanceProvider(MarketDataProvider):
    """Real Yahoo Finance provider using the public chart API.

    Works for NSE symbols by appending '.NS' (e.g. RELIANCE.NS), and for
    US symbols directly (AAPL). Public endpoints, no API key required.
    """

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self, api_key: str | None = None):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": YAHOO_USER_AGENT}, timeout=20.0, follow_redirects=True
        )
        self._semaphore = asyncio.Semaphore(5)
        self._crumb: str | None = None

    async def _get(self, url: str, params: dict | None = None) -> dict:
        async with self._semaphore:
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception:  # noqa: BLE001
                # Retry on the alternate Yahoo host (cloud IPs often get
                # redirected/rate-limited on one host but not the other).
                alt = url.replace("query1.finance.yahoo.com", "query2.finance.yahoo.com")
                if alt == url:
                    raise
                resp = await self._client.get(alt, params=params)
                resp.raise_for_status()
                return resp.json()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        sym = symbol.strip().upper()
        if "." in sym:
            return sym
        # NSE symbols are stored bare (e.g. "RELIANCE"); Yahoo needs the
        # ".NS" suffix to resolve them on the Indian exchange.
        return f"{sym}.NS"

    async def _get_crumb(self) -> str:
        """Yahoo's chart API requires a session crumb from cloud IPs; without it
        every request is rejected with HTTP 400. Fetch a fresh crumb (and the
        accompanying cookie) on demand and cache it."""
        if self._crumb:
            return self._crumb
        try:
            await self._client.get("https://fc.yahoo.com")
        except Exception:  # noqa: BLE001
            pass
        r = await self._client.get("https://query1.finance.yahoo.com/v1/test/getcrumb")
        r.raise_for_status()
        self._crumb = r.text.strip()
        return self._crumb

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        sym = self._normalize_symbol(symbol)
        params: dict[str, object] = {"interval": interval, "crumb": await self._get_crumb()}
        if start or end:
            from datetime import time as dt_time

            if start:
                params["period1"] = int(datetime.combine(start, dt_time.min).timestamp())
            if end:
                params["period2"] = int(datetime.combine(end, dt_time.min).timestamp())
        else:
            params["range"] = "1y"

        last_exc: Exception | None = None
        for base in (self.BASE_URL, "https://query2.finance.yahoo.com/v8/finance/chart"):
            try:
                async with self._semaphore:
                    resp = await self._client.get(f"{base}/{sym}", params=params)
                    resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # Crumb may have expired/been rejected; clear it and retry once.
                self._crumb = None
        else:
            assert last_exc is not None
            raise last_exc

        result = (data.get("chart") or {}).get("result")
        if not result:
            raise ValueError(f"No data returned for {symbol}")
        chart = result[0]
        timestamps = chart.get("timestamp") or []
        quote = (chart.get("indicators") or {}).get("quote") or [{}]
        quote = quote[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        points: list[MarketDataPoint] = []
        for i, ts in enumerate(timestamps):
            close = closes[i] if i < len(closes) else None
            if close is None:
                continue
            points.append(
                MarketDataPoint(
                    symbol=symbol.upper(),
                    trade_date=datetime.fromtimestamp(
                        ts, tz=datetime.now().astimezone().tzinfo
                    ).date(),
                    open=opens[i] if i < len(opens) else close,
                    high=highs[i] if i < len(highs) else close,
                    low=lows[i] if i < len(lows) else close,
                    close=close,
                    volume=int(volumes[i]) if i < len(volumes) and volumes[i] else 0,
                )
            )
        return points

    async def get_quote(self, symbol: str) -> dict:
        sym = self._normalize_symbol(symbol)
        data = await self._get(f"{self.BASE_URL}/{sym}", params={"range": "5d", "interval": "1d"})
        result = (data.get("chart") or {}).get("result")
        if not result:
            raise ValueError(f"No quote for {symbol}")
        meta = result[0].get("meta") or {}
        return {
            "symbol": meta.get("symbol", sym),
            "last_price": meta.get("regularMarketPrice"),
            "change": None,
            "change_percent": None,
            "prev_close": meta.get("chartPreviousClose"),
            "day_high": meta.get("regularMarketDayHigh"),
            "day_low": meta.get("regularMarketDayLow"),
            "volume": meta.get("regularMarketVolume"),
            "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
            "currency": meta.get("currency"),
            "name": meta.get("longName") or meta.get("shortName"),
            "exchange": meta.get("fullExchangeName"),
            "timestamp": datetime.now().isoformat(),
        }

    async def get_company_profile(self, symbol: str) -> dict:
        sym = self._normalize_symbol(symbol)
        quote = await self.get_quote(sym)
        return {
            "symbol": sym,
            "name": quote.get("name"),
            "sector": None,
            "industry": None,
            "market_cap": None,
            "exchange": (
                "NSE" if sym.endswith(".NS") else ("BSE" if sym.endswith(".BO") else "NASDAQ")
            ),
            "currency": quote.get("currency"),
        }

    async def close(self) -> None:
        await self._client.aclose()


class NSEProvider(MarketDataProvider):
    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        raise NotImplementedError("NSE provider not configured")

    async def get_quote(self, symbol: str) -> dict:
        raise NotImplementedError("NSE provider not configured")

    async def get_company_profile(self, symbol: str) -> dict:
        raise NotImplementedError("NSE provider not configured")


class StooqProvider(MarketDataProvider):
    """Free, key-less CSV historical data from Stooq.

    Works reliably from datacenter IPs (unlike Yahoo's unofficial API,
    which increasingly returns 400/429 to cloud hosts). NSE symbols use the
    '.ns' suffix (e.g. 'asianpaint.ns').
    """

    BASE_URL = "https://stooq.com/q/d/l/"

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        sym = symbol.strip().lower()
        if not (sym.endswith(".ns") or sym.endswith(".bo")):
            sym = f"{sym}.ns"
        return sym

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": YAHOO_USER_AGENT,
            "Accept": "text/csv,text/plain,*/*",
        }

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        params: dict[str, str] = {"s": self._normalize_symbol(symbol), "i": "d"}
        # Stooq 404s requests without a browser User-Agent, so send one and
        # retry on the .pl mirror if the .com host fails.
        last_exc: Exception | None = None
        for base in (self.BASE_URL, "https://stooq.pl/q/d/l/"):
            try:
                async with httpx.AsyncClient(
                    timeout=25.0, follow_redirects=True, headers=self._headers()
                ) as client:
                    resp = await client.get(base, params=params)
                    resp.raise_for_status()
                    text = resp.text.strip()
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        else:
            assert last_exc is not None
            raise last_exc
        lines = text.splitlines()
        if len(lines) < 2:
            raise ValueError(f"No data returned for {symbol}")
        points: list[MarketDataPoint] = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            date_str, o, h, l, c, v = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                points.append(
                    MarketDataPoint(
                        symbol=symbol.upper(),
                        trade_date=d,
                        open=float(o),
                        high=float(h),
                        low=float(l),
                        close=float(c),
                        volume=int(float(v)) if v else 0,
                    )
                )
            except (ValueError, TypeError):
                continue
        if not points:
            raise ValueError(f"No parseable rows for {symbol}")
        return points

    async def get_quote(self, symbol: str) -> dict:
        raise NotImplementedError("Stooq quotes not implemented")

    async def get_company_profile(self, symbol: str) -> dict:
        raise NotImplementedError("Stooq profiles not implemented")

    async def close(self) -> None:
        return None


def get_market_data_provider(provider_name: str, api_key: str | None = None) -> MarketDataProvider:
    providers = {
        "mock": MockMarketDataProvider,
        "alphavantage": lambda: AlphaVantageProvider(api_key or ""),
        "yahoo": YahooFinanceProvider,
        "nse": NSEProvider,
        "stooq": StooqProvider,
    }
    cls = providers.get(provider_name.lower())
    if cls is None:
        raise ValueError(f"Unsupported market data provider: {provider_name}")
    return cls() if provider_name.lower() in ("mock", "yahoo", "nse") else cls()
