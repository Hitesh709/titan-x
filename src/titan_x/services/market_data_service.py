import asyncio
import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice

_quote_cache: dict[str, tuple[float, dict]] = {}
_QUOTE_CACHE_TTL_SECONDS = 4.0


class MarketDataService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _resolve_provider(self, provider_name: str | None) -> str:
        if provider_name and provider_name != "default":
            candidate = provider_name.lower().strip()
        else:
            candidate = str(get_settings().market_data_provider or "yahoo").lower().strip()
        allowed = {"yahoo", "mock", "alphavantage", "stooq"}
        if candidate not in allowed:
            return "yahoo"
        return candidate

    def _provider(self, provider_name: str, api_key: str | None = None):
        return get_market_data_provider(provider_name, api_key)

    def _is_mock(self, provider_name: str) -> bool:
        return provider_name.lower() == "mock"

    async def fetch_and_store_historical(
        self,
        symbol: str,
        provider_name: str | None = None,
        api_key: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict:
        provider_name = self._resolve_provider(provider_name)
        provider = self._provider(provider_name, api_key)
        try:
            points = await provider.get_historical_prices(
                symbol,
                interval="1d",
                start=start,
                end=end,
                synthetic_ok=self._is_mock(provider_name),
            )
        finally:
            if hasattr(provider, "close"):
                await provider.close()
        symbol = symbol.upper()
        company_result = await self.session.execute(select(Company).where(Company.symbol == symbol))
        company = company_result.scalar_one_or_none()
        inserted = skipped = 0
        for point in points:
            existing_result = await self.session.execute(
                select(DailyPrice).where(
                    DailyPrice.symbol == symbol,
                    DailyPrice.trade_date == point.trade_date,
                )
            )
            if existing_result.scalar_one_or_none() is not None:
                skipped += 1
                continue
            self.session.add(
                DailyPrice(
                    symbol=symbol,
                    trade_date=point.trade_date,
                    open=point.open,
                    high=point.high,
                    low=point.low,
                    close=point.close,
                    volume=point.volume,
                )
            )
            inserted += 1
            if company is None:
                company = Company(
                    symbol=symbol,
                    company_name=f"{symbol} Corp",
                    isin=f"IN{symbol}001",
                    exchange="NSE",
                    sector="Unknown",
                )
                self.session.add(company)
        await self.session.flush()
        return {
            "symbol": symbol,
            "provider": provider_name,
            "inserted": inserted,
            "skipped": skipped,
            "total_fetched": len(points),
        }

    async def ingest_universe(
        self,
        symbols: list[str],
        provider_name: str | None = None,
        api_key: str | None = None,
        start: date | None = None,
        end: date | None = None,
        max_concurrency: int = 1,
    ) -> dict:
        provider_name = self._resolve_provider(provider_name)
        results = []
        for symbol in symbols:
            try:
                results.append(
                    await self.fetch_and_store_historical(
                        symbol,
                        provider_name=provider_name,
                        api_key=api_key,
                        start=start,
                        end=end,
                    )
                )
            except Exception as exc:
                results.append(
                    {"symbol": symbol.upper(), "provider": provider_name, "error": str(exc)}
                )
        errors = [r for r in results if "error" in r]
        return {
            "provider": provider_name,
            "symbols_requested": len(symbols),
            "symbols_ok": len(results) - len(errors),
            "symbols_failed": len(errors),
            "inserted_total": sum(r.get("inserted", 0) for r in results),
            "errors": errors,
        }

    async def get_quote(
        self,
        symbol: str,
        provider_name: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        provider_name = self._resolve_provider(provider_name)
        provider = self._provider(provider_name, api_key)
        try:
            quote = await provider.get_quote(symbol.upper())
            self._normalize_quote_change(quote)
            return quote
        finally:
            if hasattr(provider, "close"):
                await provider.close()

    @staticmethod
    def _normalize_quote_change(q: dict) -> dict:
        last = q.get("last_price")
        prev = q.get("prev_close")
        if q.get("change") is None and last is not None and prev not in (None, 0):
            q["change"] = float(last) - float(prev)
        if q.get("change_percent") is None and q.get("change") is not None and prev not in (None, 0):
            q["change_percent"] = float(q["change"]) / float(prev) * 100.0
        return q

    async def get_quotes(self, symbols: list[str]) -> dict:
        symbols = list(
            dict.fromkeys(
                s.upper().replace(".NS", "").replace(".BO", "")
                for s in symbols
                if s.strip()
            )
        )[:100]
        now = time.monotonic()
        out: list[dict] = []
        to_fetch: list[str] = []
        for symbol in symbols:
            hit = _quote_cache.get(symbol)
            if hit and now - hit[0] < _QUOTE_CACHE_TTL_SECONDS and hit[1].get("last_price") is not None:
                out.append(hit[1])
            else:
                to_fetch.append(symbol)

        provider_name = self._resolve_provider(None)
        provider = self._provider(provider_name)
        try:
            for start in range(0, len(to_fetch), 10):
                batch = to_fetch[start : start + 10]
                results = await asyncio.gather(
                    *(self._fetch_quote_with_retry(provider, symbol) for symbol in batch),
                    return_exceptions=True,
                )
                for symbol, result in zip(batch, results):
                    if isinstance(result, dict) and result.get("last_price") is not None:
                        self._normalize_quote_change(result)
                        _quote_cache[symbol] = (time.monotonic(), result)
                        out.append(result)
                if start + 10 < len(to_fetch):
                    await asyncio.sleep(0.4)
        finally:
            if hasattr(provider, "close"):
                await provider.close()

        order = {symbol: i for i, symbol in enumerate(symbols)}
        out.sort(
            key=lambda q: order.get(
                str(q.get("symbol", "")).replace(".NS", "").replace(".BO", ""),
                9999,
            )
        )
        return {
            "quotes": out,
            "count": len(out),
            "requested": len(symbols),
            "live": True,
            "provider": provider_name,
            "source": provider_name,
        }

    async def _fetch_quote_with_retry(self, provider, symbol: str) -> dict | None:
        for attempt in range(3):
            try:
                return await provider.get_quote(symbol)
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.8 * (attempt + 1))
        return None

    async def get_company_profile(
        self,
        symbol: str,
        provider_name: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        symbol = symbol.upper()
        company = (
            await self.session.execute(select(Company).where(Company.symbol == symbol))
        ).scalar_one_or_none()
        if company is not None:
            return {
                "symbol": company.symbol,
                "name": company.company_name,
                "isin": company.isin,
                "exchange": company.exchange,
                "sector": company.sector,
                "industry": company.industry,
                "market_cap": company.market_cap,
                "currency": "INR",
                "description": company.description,
                "website": company.website,
                "listing_date": company.listing_date.isoformat() if company.listing_date else None,
            }
        try:
            provider_name = self._resolve_provider(provider_name)
            provider = self._provider(provider_name, api_key)
            try:
                profile = await provider.get_company_profile(symbol)
            finally:
                if hasattr(provider, "close"):
                    await provider.close()
        except Exception:
            profile = None
        return profile or {
            "symbol": symbol,
            "name": symbol,
            "exchange": "NSE",
            "sector": None,
            "industry": None,
            "market_cap": None,
            "currency": "INR",
        }

    async def get_history(
        self,
        symbol: str,
        provider_name: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        symbol = symbol.upper()
        existing = (
            await self.session.execute(
                select(DailyPrice)
                .where(DailyPrice.symbol == symbol)
                .order_by(DailyPrice.trade_date.asc())
            )
        ).scalars().all()
        if existing:
            return {
                "symbol": symbol,
                "points": [
                    {
                        "trade_date": p.trade_date.isoformat(),
                        "open": p.open,
                        "high": p.high,
                        "low": p.low,
                        "close": p.close,
                        "volume": p.volume,
                    }
                    for p in existing
                ],
            }
        return {"symbol": symbol, "points": []}

    def get_available_providers(self) -> list[str]:
        return ["yahoo", "mock", "alphavantage", "stooq"]


async def load_active_symbols(
    session: AsyncSession,
    symbol: str | None = None,
    limit: int = 100,
) -> list[str]:
    if symbol:
        return [symbol.strip().upper()]
    stmt = select(Company.symbol).where(Company.status == "active").limit(limit)
    result = await session.execute(stmt)
    return [r[0] for r in result.all()]


async def run_market_data_ingestion(
    session_factory: Any,
    symbol: str | None = None,
    provider_name: str | None = None,
    max_symbols: int = 100,
    lookback_days: int = 365,
) -> dict:
    async with session_factory() as session:
        symbols = await load_active_symbols(session, symbol=symbol, limit=max_symbols)
        svc = MarketDataService(session)
        start = date.today() - timedelta(days=lookback_days)
        result = await svc.ingest_universe(
            symbols,
            provider_name=provider_name,
            start=start,
            max_concurrency=1,
        )
        await session.commit()
        return result
