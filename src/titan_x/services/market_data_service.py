from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.infrastructure.market_data_providers import (
    MarketDataProvider,
    get_market_data_provider,
)
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice


class MarketDataService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch_and_store_historical(
        self,
        symbol: str,
        provider_name: str = "mock",
        api_key: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict:
        provider = get_market_data_provider(provider_name, api_key)
        points = await provider.get_historical_prices(symbol, start=start, end=end)

        company_stmt = select(Company).where(Company.symbol == symbol.upper())
        company_result = await self.session.execute(company_stmt)
        company = company_result.scalar_one_or_none()

        inserted = 0
        skipped = 0
        for point in points:
            existing_stmt = select(DailyPrice).where(
                DailyPrice.symbol == symbol.upper(),
                DailyPrice.trade_date == point.trade_date,
            )
            existing_result = await self.session.execute(existing_stmt)
            if existing_result.scalar_one_or_none() is not None:
                skipped += 1
                continue

            dp = DailyPrice(
                symbol=symbol.upper(),
                trade_date=point.trade_date,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
            )
            self.session.add(dp)
            inserted += 1

            if company is None:
                company = Company(
                    symbol=symbol.upper(),
                    company_name=f"{symbol.upper()} Corp",
                    isin=f"IN{symbol.upper()}001",
                    exchange="NSE",
                    sector="Unknown",
                )
                self.session.add(company)

        await self.session.flush()
        return {
            "symbol": symbol.upper(),
            "provider": provider_name,
            "inserted": inserted,
            "skipped": skipped,
            "total_fetched": len(points),
        }

    async def get_quote(
        self,
        symbol: str,
        provider_name: str = "mock",
        api_key: str | None = None,
    ) -> dict:
        provider = get_market_data_provider(provider_name, api_key)
        return await provider.get_quote(symbol.upper())

    async def get_company_profile(
        self,
        symbol: str,
        provider_name: str = "mock",
        api_key: str | None = None,
    ) -> dict:
        provider = get_market_data_provider(provider_name, api_key)
        profile = await provider.get_company_profile(symbol.upper())

        company_stmt = select(Company).where(Company.symbol == symbol.upper())
        company_result = await self.session.execute(company_stmt)
        company = company_result.scalar_one_or_none()

        if company is None:
            company = Company(
                symbol=symbol.upper(),
                company_name=profile.get("name", f"{symbol.upper()} Corp"),
                isin=f"IN{symbol.upper()}001",
                exchange=profile.get("exchange", "NSE"),
                sector=profile.get("sector", "Unknown"),
                industry=profile.get("industry"),
                market_cap=profile.get("market_cap"),
            )
            self.session.add(company)
            await self.session.flush()

        return profile

    def get_available_providers(self) -> list[str]:
        return ["mock", "alphavantage", "yahoo", "nse"]
