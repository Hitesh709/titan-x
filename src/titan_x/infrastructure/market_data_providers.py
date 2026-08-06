from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Any

import httpx

from titan_x.core.time import utcnow


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
        synthetic_ok: bool = True,
    ) -> list[MarketDataPoint]: ...

    @abstractmethod
    async def get_quote(self, symbol: str, synthetic_ok: bool = True) -> dict: ...

    @abstractmethod
    async def get_company_profile(self, symbol: str, synthetic_ok: bool = True) -> dict: ...

    async def search_symbols(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search for tradable symbols/companies by name or ticker.

        Default implementation queries the locally stored companies so the
        behaviour degrades gracefully for providers without a search API.
        Real providers may override with a network-backed search.
        """
        return []


class MockMarketDataProvider(MarketDataProvider):
    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = True,
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

    async def get_quote(self, symbol: str, synthetic_ok: bool = True) -> dict:
        return {
            "symbol": symbol,
            "last_price": 150.0,
            "change": 2.5,
            "change_percent": 1.67,
            "volume": 2_500_000,
            "timestamp": utcnow().isoformat(),
        }

    async def get_company_profile(self, symbol: str, synthetic_ok: bool = True) -> dict:
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
        synthetic_ok: bool = True,
    ) -> list[MarketDataPoint]:
        raise NotImplementedError("Alpha Vantage not configured")

    async def get_quote(self, symbol: str, synthetic_ok: bool = True) -> dict:
        raise NotImplementedError("Alpha Vantage not configured")

    async def get_company_profile(self, symbol: str, synthetic_ok: bool = True) -> dict:
        raise NotImplementedError("Alpha Vantage not configured")


class YahooFinanceProvider(MarketDataProvider):
    """Real-time market data via Yahoo Finance public endpoints.

    Free, no API key. For the Indian market NSE symbols are addressed with the
    ``.NS`` suffix (BSE with ``.BO``); the NIFTY 50 index is ``^NSEI`` and the
    Sensex is ``^BSESN``. Any failure falls back to synthetic data so the
    application keeps serving even when the upstream is unreachable.
    """

    _BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None
        self._timeout = httpx.Timeout(10.0, connect=5.0)

    @staticmethod
    def _yahoo_symbol(symbol: str) -> str:
        s = symbol.strip().upper()
        if s.startswith("^"):
            return s
        if s.endswith((".NS", ".BO")):
            return s
        return f"{s}.NS"

    @staticmethod
    def _exchange_name(code: str) -> str:
        code = (code or "").upper()
        if code in ("NSI", "NSE"):
            return "NSE"
        if code in ("BOM", "BSI", "BSE"):
            return "BSE"
        return code or "NSE"

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._HEADERS,
                timeout=self._timeout,
                limits=httpx.Limits(
                    max_connections=20, max_keepalive_connections=10, keepalive_expiry=30
                ),
            )
        return self._client

    async def _chart(self, symbol: str, range_: str = "1d", interval: str = "1m") -> dict:
        client = await self._ensure_client()
        url = f"{self._BASE}/{self._yahoo_symbol(symbol)}"
        resp = await client.get(
            url,
            params={"range": range_, "interval": interval, "region": "IN", "lang": "en-IN"},
        )
        resp.raise_for_status()
        payload = resp.json()
        results = (payload.get("chart") or {}).get("result")
        if not results:
            raise RuntimeError(f"No chart data for {symbol}")
        return results[0]

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = True,
    ) -> list[MarketDataPoint]:
        try:
            data = await self._chart(symbol, range_="1y", interval="1d")
            timestamps = data.get("timestamp") or []
            quote = ((data.get("indicators") or {}).get("quote") or [{}])[0] or {}
            opens, highs, lows, closes, volumes = (
                quote.get("open") or [],
                quote.get("high") or [],
                quote.get("low") or [],
                quote.get("close") or [],
                quote.get("volume") or [],
            )
            points: list[MarketDataPoint] = []
            for i, ts in enumerate(timestamps):
                close = closes[i] if i < len(closes) else None
                if close is None or close is None:
                    continue
                trade_date = date.fromtimestamp(ts)
                if start and trade_date < start:
                    continue
                if end and trade_date > end:
                    continue
                points.append(
                    MarketDataPoint(
                        symbol=symbol.upper(),
                        trade_date=trade_date,
                        open=opens[i] if i < len(opens) else close,
                        high=highs[i] if i < len(highs) else close,
                        low=lows[i] if i < len(lows) else close,
                        close=close,
                        volume=int(volumes[i])
                        if i < len(volumes) and volumes[i] is not None
                        else 0,
                    )
                )
            if not points:
                raise RuntimeError(f"No historical rows for {symbol}")
            return points
        except Exception:
            if not synthetic_ok:
                raise
            return await MockMarketDataProvider().get_historical_prices(
                symbol, start=start, end=end
            )

    async def get_quote(self, symbol: str, synthetic_ok: bool = True) -> dict:
        try:
            data = await self._chart(symbol, range_="1d", interval="1m")
            meta = data.get("meta") or {}
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
            change = round((price - prev), 2) if price is not None and prev is not None else 0.0
            change_pct = round(change / prev * 100, 2) if prev else 0.0
            return {
                "symbol": symbol.upper(),
                "name": meta.get("longName") or meta.get("shortName") or f"{symbol.upper()} Ltd",
                "last_price": price,
                "change": change,
                "change_percent": change_pct,
                "volume": meta.get("regularMarketVolume", 0),
                "market_cap": meta.get("marketCap"),
                "exchange": self._exchange_name(meta.get("exchangeName") or "NSE"),
                "market_state": meta.get("marketState") or "REGULAR",
                "currency": meta.get("currency") or "INR",
                "timestamp": utcnow().isoformat(),
                "source": "yahoo",
            }
        except Exception:
            if not synthetic_ok:
                raise
            return {**MockMarketDataProvider().get_quote(symbol), "source": "yahoo-fallback"}

    async def get_company_profile(self, symbol: str, synthetic_ok: bool = True) -> dict:
        try:
            data = await self._chart(symbol, range_="5d", interval="1d")
            meta = data.get("meta") or {}
            return {
                "symbol": symbol.upper(),
                "name": meta.get("longName") or meta.get("shortName") or f"{symbol.upper()} Ltd",
                "sector": meta.get("sector") or "Equity",
                "industry": meta.get("industry") or "Equity",
                "market_cap": meta.get("marketCap"),
                "exchange": self._exchange_name(meta.get("exchangeName") or "NSE"),
                "currency": meta.get("currency") or "INR",
                "source": "yahoo",
            }
        except Exception:
            if not synthetic_ok:
                raise
            return MockMarketDataProvider().get_company_profile(symbol)

    async def search_symbols(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            client = await self._ensure_client()
            resp = await client.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={
                    "q": query,
                    "quotesCount": limit,
                    "newsCount": 0,
                    "region": "IN",
                    "lang": "en-IN",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            quotes = payload.get("quotes") or []
            out: list[dict[str, Any]] = []
            for item in quotes:
                symbol = str(item.get("symbol") or "").upper().strip()
                exchange = str(item.get("exchange") or "").upper().strip()
                if not symbol:
                    continue
                out.append(
                    {
                        "symbol": symbol,
                        "company_name": item.get("longname") or item.get("shortname") or symbol,
                        "exchange": self._exchange_name(item.get("exchDisp") or exchange),
                        "sector": item.get("sector"),
                        "industry": item.get("industry"),
                        "market_cap": item.get("marketCap"),
                        "source": "yahoo",
                    }
                )
            return out[:limit]
        except Exception:
            return []


class NSEProvider(MarketDataProvider):
    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = True,
    ) -> list[MarketDataPoint]:
        raise NotImplementedError("NSE provider not configured")

    async def get_quote(self, symbol: str, synthetic_ok: bool = True) -> dict:
        raise NotImplementedError("NSE provider not configured")

    async def get_company_profile(self, symbol: str, synthetic_ok: bool = True) -> dict:
        raise NotImplementedError("NSE provider not configured")


def get_market_data_provider(provider_name: str, api_key: str | None = None) -> MarketDataProvider:
    providers = {
        "mock": MockMarketDataProvider,
        "alphavantage": lambda: AlphaVantageProvider(api_key or ""),
        "yahoo": YahooFinanceProvider,
        "nse": NSEProvider,
    }
    cls = providers.get(provider_name.lower())
    if cls is None:
        raise ValueError(f"Unsupported market data provider: {provider_name}")
    return cls() if provider_name.lower() in ("mock", "yahoo", "nse") else cls()
