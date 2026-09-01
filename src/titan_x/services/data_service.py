"""Compatibility service for market data access."""

from __future__ import annotations

from datetime import date

from titan_x.infrastructure.market_data_providers import (
    MarketDataPoint,
    get_market_data_provider,
)


class DataService:
    """Thin facade over the existing provider abstraction.

    Keep provider selection here instead of creating provider-specific logic in
    API routers. Yahoo is supported through the existing provider implementation
    and can be selected without an API key or static-IP dependency.
    """

    def __init__(self, provider_name: str = "yahoo", api_key: str | None = None):
        self.provider_name = provider_name.lower()
        self.provider = get_market_data_provider(self.provider_name, api_key)

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        return await self.provider.get_historical_prices(
            symbol,
            interval=interval,
            start=start,
            end=end,
            synthetic_ok=synthetic_ok,
        )

    async def get_quote(self, symbol: str) -> dict:
        return await self.provider.get_quote(symbol)

    async def get_company_profile(self, symbol: str) -> dict:
        return await self.provider.get_company_profile(symbol)

    async def close(self) -> None:
        await self.provider.close()
