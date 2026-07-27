from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta


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
        self, symbol: str, interval: str = "1d", start: date | None = None, end: date | None = None
    ) -> list[MarketDataPoint]:
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict:
        ...

    @abstractmethod
    async def get_company_profile(self, symbol: str) -> dict:
        ...


class MockMarketDataProvider(MarketDataProvider):
    async def get_historical_prices(
        self, symbol: str, interval: str = "1d", start: date | None = None, end: date | None = None
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
                points.append(MarketDataPoint(
                    symbol=symbol,
                    trade_date=current,
                    open=price,
                    high=price + 2,
                    low=price - 2,
                    close=price + 0.5,
                    volume=1_000_000 + (hash(f"{symbol}_v{i}") % 500_000),
                ))
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
        self, symbol: str, interval: str = "1d", start: date | None = None, end: date | None = None
    ) -> list[MarketDataPoint]:
        raise NotImplementedError("Alpha Vantage not configured")

    async def get_quote(self, symbol: str) -> dict:
        raise NotImplementedError("Alpha Vantage not configured")

    async def get_company_profile(self, symbol: str) -> dict:
        raise NotImplementedError("Alpha Vantage not configured")


class YahooFinanceProvider(MarketDataProvider):
    async def get_historical_prices(
        self, symbol: str, interval: str = "1d", start: date | None = None, end: date | None = None
    ) -> list[MarketDataPoint]:
        raise NotImplementedError("Yahoo Finance not configured")

    async def get_quote(self, symbol: str) -> dict:
        raise NotImplementedError("Yahoo Finance not configured")

    async def get_company_profile(self, symbol: str) -> dict:
        raise NotImplementedError("Yahoo Finance not configured")


class NSEProvider(MarketDataProvider):
    async def get_historical_prices(
        self, symbol: str, interval: str = "1d", start: date | None = None, end: date | None = None
    ) -> list[MarketDataPoint]:
        raise NotImplementedError("NSE provider not configured")

    async def get_quote(self, symbol: str) -> dict:
        raise NotImplementedError("NSE provider not configured")

    async def get_company_profile(self, symbol: str) -> dict:
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
