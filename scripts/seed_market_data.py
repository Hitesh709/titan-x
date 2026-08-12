#!/usr/bin/env python
"""Seed companies + daily prices from real Yahoo Finance data for NSE symbols.

Usage:
  python scripts/seed_market_data.py            # default universe
  python scripts/seed_market_data.py --symbols RELIANCE TCS INFY   # subset
"""
import argparse
import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from titan_x.core.config import get_settings
from titan_x.db.base import Base
from titan_x.db.session import create_engine, create_session_factory
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models import *  # noqa: F401, F403 - register all models
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice

NSE_LARGE_CAP = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
    "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "BAJFINANCE",
    "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN", "HCLTECH", "SUNPHARMA",
    "ULTRACEMCO", "WIPRO", "TATAMOTORS", "NTPC", "POWERGRID", "ADANIENT",
    "ADANIPORTS", "TATASTEEL", "JSWSTEEL", "ONGC", "COALINDIA", "BAJAJFINSV",
    "NESTLEIND", "DLF", "EICHERMOT", "GRASIM", "HINDALCO", "DRREDDY",
    "DIVISLAB", "BPCL", "GAIL", "HEROMOTOCO", "TECHM", "SBILIFE",
    "INDUSINDBK", "CIPLA", "APOLLOHOSP", "BRITANNIA", "TATAPOWER", "HDFCLIFE",
    "LUPIN", "PIDILITIND",
]


async def upsert_company(provider, session, raw_symbol: str) -> Company | None:
    sym = raw_symbol.upper()
    if not sym.endswith(".NS"):
        sym = f"{sym}.NS"
    try:
        profile = await provider.get_company_profile(sym)
        quote = await provider.get_quote(sym)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {raw_symbol}: profile/quote failed: {exc}")
        return None

    name = (profile.get("name") or raw_symbol).strip()
    sector = profile.get("sector")
    industry = profile.get("industry")
    market_cap = quote.get("market_cap")

    existing = await session.execute(select(Company).where(Company.symbol == sym))
    company = existing.scalar_one_or_none()
    if company is None:
        company = Company(
            symbol=sym,
            company_name=name,
            isin=f"SEED{sym.replace('.', '')[:8]}",
            sector=sector,
            industry=industry,
            exchange="NSE",
            market_cap=market_cap,
            status="active",
        )
        session.add(company)
        print(f"  + {raw_symbol}: created company '{name}'")
    else:
        company.company_name = name
        company.sector = sector
        company.industry = industry
        if market_cap:
            company.market_cap = market_cap
        print(f"  = {raw_symbol}: updated company '{name}'")
    await session.flush()
    return company


async def sync_prices(provider, session, symbol: str) -> int:
    sym = symbol if symbol.endswith((".NS", ".BO")) else f"{symbol}.NS"
    end = date.today()
    start = end - timedelta(days=400)
    try:
        points = await provider.get_historical_prices(sym, interval="1d", start=start, end=end)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {sym}: prices failed: {exc}")
        return 0

    inserted = 0
    for p in points:
        existing = await session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == sym, DailyPrice.trade_date == p.trade_date,
            )
        )
        if existing.scalar_one_or_none():
            continue
        session.add(DailyPrice(
            symbol=sym,
            trade_date=p.trade_date,
            open=p.open, high=p.high, low=p.low, close=p.close, volume=p.volume,
        ))
        inserted += 1
    return inserted


async def run(symbols: list[str]) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    provider = YahooFinanceProvider()
    async with factory() as session:
        for raw in symbols:
            print(f"== {raw} ==")
            company = await upsert_company(provider, session, raw)
            if company is None:
                continue
            n = await sync_prices(provider, session, raw)
            print(f"   inserted {n} daily prices")
        await session.commit()
    await provider.close()

    # Report totals
    async with factory() as session:
        n_companies = (await session.execute(select(Company).count())).scalar() or 0
        n_prices = (await session.execute(select(DailyPrice).count())).scalar() or 0
        print(f"\nDONE: {n_companies} companies, {n_prices} daily price rows")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="*", default=NSE_LARGE_CAP)
    args = parser.parse_args()
    asyncio.run(run(args.symbols))
