import asyncio
import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice

_quote_cache: dict[str, tuple[float, dict]] = {}
_QUOTE_CACHE_TTL_SECONDS = 4.0
_SUPPORTED_PROVIDERS = {"mock", "alphavantage", "yahoo", "nse", "stooq"}


class MarketDataService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _resolve_provider(self, provider_name: str | None) -> str:
        name = (provider_name or "yahoo").lower().strip()
        if name == "default":
            return "yahoo"
        if name not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported market data provider: {provider_name}")
        return name

    def _provider(self, provider_name: str = "yahoo", api_key: str | None = None):
        return get_market_data_provider(self._resolve_provider(provider_name), api_key)

    async def fetch_and_store_historical(self, symbol: str, provider_name: str | None = None, api_key: str | None = None, start: date | None = None, end: date | None = None) -> dict:
        symbol = symbol.upper()
        provider_name = self._resolve_provider(provider_name)
        provider = self._provider(provider_name, api_key)
        try:
            points = await provider.get_historical_prices(symbol, interval="1d", start=start, end=end, synthetic_ok=provider_name == "mock")
            profile = await provider.get_company_profile(symbol)
        finally:
            await provider.close()

        company = (await self.session.execute(select(Company).where(Company.symbol == symbol))).scalar_one_or_none()
        inserted = skipped = 0
        for point in points:
            exists = (await self.session.execute(select(DailyPrice).where(DailyPrice.symbol == symbol, DailyPrice.trade_date == point.trade_date))).scalar_one_or_none()
            if exists:
                skipped += 1
                continue
            self.session.add(DailyPrice(symbol=symbol, trade_date=point.trade_date, open=point.open, high=point.high, low=point.low, close=point.close, volume=point.volume))
            inserted += 1

        if company is None:
            self.session.add(Company(symbol=symbol, company_name=profile.get("name") or f"{symbol} Corp", isin="IN" + symbol[:10], exchange=profile.get("exchange") or "NSE", sector=profile.get("sector") or "Unknown", status="active"))
        await self.session.flush()
        return {"symbol": symbol, "provider": provider_name, "inserted": inserted, "skipped": skipped, "total_fetched": len(points)}

    async def ingest_universe(self, symbols: list[str], provider_name: str | None = None, api_key: str | None = None, start: date | None = None, end: date | None = None, max_concurrency: int = 1) -> dict:
        provider_name = self._resolve_provider(provider_name)
        results = []
        for symbol in symbols:
            try:
                results.append(await self.fetch_and_store_historical(symbol, provider_name, api_key, start=start, end=end))
            except Exception as exc:
                results.append({"symbol": symbol.upper(), "provider": provider_name, "error": str(exc)})
        errors = [result for result in results if "error" in result]
        return {"provider": provider_name, "symbols_requested": len(symbols), "symbols_ok": len(results) - len(errors), "symbols_failed": len(errors), "inserted_total": sum(result.get("inserted", 0) for result in results), "errors": errors}

    async def get_quote(self, symbol: str, provider_name: str | None = None, api_key: str | None = None) -> dict:
        provider = self._provider(provider_name or "yahoo", api_key)
        try:
            quote = await provider.get_quote(symbol.upper())
            return self._normalize_quote_change(quote)
        finally:
            await provider.close()

    @staticmethod
    def _normalize_quote_change(q: dict) -> dict:
        last, previous = q.get("last_price"), q.get("prev_close")
        if q.get("change") is None and last is not None and previous not in (None, 0):
            q["change"] = float(last) - float(previous)
        if q.get("change_percent") is None and q.get("change") is not None and previous not in (None, 0):
            q["change_percent"] = float(q["change"]) / float(previous) * 100
        return q

    async def get_quotes(self, symbols: list[str]) -> dict:
        symbols = list(dict.fromkeys(s.upper().replace(".NS", "").replace(".BO", "") for s in symbols if s.strip()))[:100]
        now = time.monotonic()
        output = []
        todo = []
        for symbol in symbols:
            hit = _quote_cache.get(symbol)
            if hit and now - hit[0] < _QUOTE_CACHE_TTL_SECONDS and hit[1].get("last_price") is not None:
                output.append(hit[1])
            else:
                todo.append(symbol)

        provider = self._provider()
        try:
            for start_index in range(0, len(todo), 10):
                batch = todo[start_index : start_index + 10]
                results = await asyncio.gather(*(self._fetch_quote_with_retry(provider, symbol) for symbol in batch), return_exceptions=True)
                for symbol, result in zip(batch, results):
                    if isinstance(result, dict) and result.get("last_price") is not None:
                        self._normalize_quote_change(result)
                        _quote_cache[symbol] = (time.monotonic(), result)
                        output.append(result)
                if start_index + 10 < len(todo):
                    await asyncio.sleep(0.4)
        finally:
            await provider.close()

        order = {symbol: index for index, symbol in enumerate(symbols)}
        output.sort(key=lambda quote: order.get(str(quote.get("symbol", "")).replace(".NS", "").replace(".BO", ""), 9999))
        return {"quotes": output, "count": len(output), "requested": len(symbols), "live": True, "provider": "yahoo", "source": "yahoo"}

    async def _fetch_quote_with_retry(self, provider, symbol):
        for attempt in range(3):
            try:
                return await provider.get_quote(symbol)
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.8 * (attempt + 1))
        return None

    async def get_company_profile(self, symbol: str, provider_name: str | None = None, api_key: str | None = None) -> dict:
        symbol = symbol.upper()
        company = (await self.session.execute(select(Company).where(Company.symbol == symbol))).scalar_one_or_none()
        if company:
            return {"symbol": company.symbol, "name": company.company_name, "isin": company.isin, "exchange": company.exchange, "sector": company.sector, "industry": company.industry, "market_cap": company.market_cap, "currency": "INR", "description": company.description, "website": company.website, "listing_date": company.listing_date.isoformat() if company.listing_date else None}
        provider = self._provider(provider_name or "yahoo", api_key)
        try:
            profile = await provider.get_company_profile(symbol)
        finally:
            await provider.close()

        # A profile lookup is a company-discovery operation. Persist it so the
        # database-backed company endpoints can immediately resolve the symbol.
        existing = (await self.session.execute(select(Company).where(Company.symbol == symbol))).scalar_one_or_none()
        if existing is None:
            self.session.add(Company(symbol=symbol, company_name=profile.get("name") or f"{symbol} Corp", isin=profile.get("isin") or "IN" + symbol[:10], exchange=profile.get("exchange") or "NSE", sector=profile.get("sector") or "Unknown", industry=profile.get("industry"), market_cap=profile.get("market_cap"), status="active"))
            await self.session.flush()
        return profile

    async def get_history(self, symbol: str, provider_name: str | None = None, api_key: str | None = None) -> dict:
        rows = (await self.session.execute(select(DailyPrice).where(DailyPrice.symbol == symbol.upper()).order_by(DailyPrice.trade_date.asc()))).scalars().all()
        return {"symbol": symbol.upper(), "points": [{"trade_date": price.trade_date.isoformat(), "open": price.open, "high": price.high, "low": price.low, "close": price.close, "volume": price.volume} for price in rows]}

    def get_available_providers(self) -> list[str]:
        return ["mock", "alphavantage", "yahoo", "nse", "stooq"]


async def load_active_symbols(session: AsyncSession, symbol: str | None = None, limit: int = 100) -> list[str]:
    if symbol:
        return [symbol.strip().upper()]
    result = await session.execute(select(Company.symbol).where(Company.status == "active").limit(limit))
    return [row[0] for row in result.all()]


async def run_market_data_ingestion(session_factory: Any, symbol: str | None = None, provider_name: str | None = None, max_symbols: int = 100, lookback_days: int = 365) -> dict:
    provider_name = provider_name or "yahoo"
    async with session_factory() as session:
        symbols = await load_active_symbols(session, symbol=symbol, limit=max_symbols)
        result = await MarketDataService(session).ingest_universe(symbols, provider_name, start=date.today() - timedelta(days=lookback_days))
        await session.commit()
        return result
