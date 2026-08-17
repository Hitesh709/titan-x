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
            return provider_name
        return get_settings().market_data_provider

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
        provider = get_market_data_provider(provider_name, api_key)
        points = await provider.get_historical_prices(
            symbol, start=start, end=end, synthetic_ok=self._is_mock(provider_name)
        )

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

    async def ingest_universe(
        self,
        symbols: list[str],
        provider_name: str | None = None,
        api_key: str | None = None,
        start: date | None = None,
        end: date | None = None,
        max_concurrency: int = 4,
    ) -> dict:
        """Fetch and store real OHLCV history for many symbols.

        Failures are isolated per symbol so one bad ticker does not abort the
        batch; real providers never silently persist synthetic data.
        """
        provider_name = self._resolve_provider(provider_name)

        results: list[dict] = [None] * len(symbols)
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(idx: int, symbol: str) -> None:
            async with sem:
                try:
                    results[idx] = await self.fetch_and_store_historical(
                        symbol,
                        provider_name=provider_name,
                        api_key=api_key,
                        start=start,
                        end=end,
                    )
                except Exception as exc:  # noqa: BLE001
                    results[idx] = {
                        "symbol": symbol.upper(),
                        "provider": provider_name,
                        "error": str(exc),
                    }

        await asyncio.gather(*[_fetch_one(i, s) for i, s in enumerate(symbols)])
        results = [r for r in results if r is not None]

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
        provider = get_market_data_provider(provider_name, api_key)
        return await provider.get_quote(symbol.upper(), synthetic_ok=self._is_mock(provider_name))

    async def get_quotes(self, symbols: list[str]) -> dict:
        """Live quotes for many symbols in parallel, deduplicated by a short cache."""
        symbols = [s.upper() for s in symbols]
        provider = get_market_data_provider(self._resolve_provider(None))
        now = time.monotonic()
        out: list[dict] = []
        to_fetch: list[str] = []
        for s in symbols:
            hit = _quote_cache.get(s)
            if hit and now - hit[0] < _QUOTE_CACHE_TTL_SECONDS:
                out.append(hit[1])
            else:
                to_fetch.append(s)
                out.append(None)
        if to_fetch:
            try:
                results = await asyncio.gather(
                    *[provider.get_quote(s) for s in to_fetch],
                    return_exceptions=True,
                )
            finally:
                if hasattr(provider, "close"):
                    await provider.close()
            fi = 0
            for i, s in enumerate(symbols):
                if out[i] is None:
                    res = results[fi]
                    fi += 1
                    q = (
                        res
                        if not isinstance(res, Exception)
                        else {
                            "symbol": s,
                            "name": s,
                            "last_price": None,
                            "change": None,
                            "change_percent": None,
                            "volume": 0,
                            "exchange": "NSE",
                            "currency": "INR",
                            "source": "error",
                        }
                    )
                    _quote_cache[s] = (now, q)
                    out[i] = q
        return {"quotes": out, "count": len(out)}

    async def get_company_profile(
        self,
        symbol: str,
        provider_name: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        symbol = symbol.upper()
        # Prefer the local company record (always present for seeded/universe
        # symbols). This avoids an external call on the hot path and means the
        # endpoint never 500s just because the live provider is unavailable.
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

        # Fallback to the provider only when we have no local record.
        try:
            provider_name = self._resolve_provider(provider_name)
            provider = get_market_data_provider(provider_name, api_key)
            profile = await provider.get_company_profile(
                symbol, synthetic_ok=self._is_mock(provider_name)
            )
        except Exception:  # noqa: BLE001
            profile = None
        if not profile:
            # No data anywhere: return a safe minimal profile so the UI can
            # render gracefully instead of receiving a 500.
            return {
                "symbol": symbol,
                "name": symbol,
                "exchange": "NSE",
                "sector": None,
                "industry": None,
                "market_cap": None,
                "currency": "INR",
            }
        return profile

    async def get_history(
        self,
        symbol: str,
        provider_name: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        symbol = symbol.upper()
        # Prefer locally stored daily prices (seeded/ingested) — always safe.
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

        # Fallback to the provider only when there is no local history.
        try:
            provider_name = self._resolve_provider(provider_name)
            provider = get_market_data_provider(provider_name, api_key)
            try:
                points = await provider.get_historical_prices(
                    symbol, synthetic_ok=self._is_mock(provider_name)
                )
            finally:
                if hasattr(provider, "close"):
                    await provider.close()
        except Exception:  # noqa: BLE001
            points = None
        if not points:
            return {"symbol": symbol, "points": []}
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
                for p in points
            ],
        }

    def get_available_providers(self) -> list[str]:
        return ["mock", "alphavantage", "yahoo", "nse"]


async def load_active_symbols(
    session: AsyncSession, symbol: str | None = None, limit: int = 100
) -> list[str]:
    """Resolve the list of symbols to ingest: explicit symbol, else the active
    company universe, else a small curated default set so nothing is empty."""
    from titan_x.core.seed_demo import COMPANIES

    if symbol:
        return [symbol.strip().upper()]

    from titan_x.models.company import Company

    stmt = select(Company.symbol).where(Company.status == "active").limit(limit)
    result = await session.execute(stmt)
    rows = [r[0] for r in result.all()]
    if rows:
        return rows

    return [c[0] for c in COMPANIES if c[0]][:limit]


async def run_market_data_ingestion(
    session_factory: Any,
    symbol: str | None = None,
    provider_name: str | None = None,
    max_symbols: int = 100,
    lookback_days: int = 365,
) -> dict:
    """Persist real OHLCV history for the active universe (or a single symbol)
    using the configured real provider. Returns a summary dict."""
    async with session_factory() as session:  # type: ignore[union-attr]
        symbols = await load_active_symbols(session, symbol=symbol, limit=max_symbols)
        svc = MarketDataService(session)
        start = date.today() - timedelta(days=lookback_days)
        result = await svc.ingest_universe(
            symbols,
            provider_name=provider_name,
            start=start,
            max_concurrency=4,
        )
        await session.commit()
        return result
