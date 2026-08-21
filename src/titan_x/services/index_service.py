import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.index_price import IndexDaily

# (symbol, name, base, drift_pct, volatility_pct)
INDICES = [
    ("NIFTY", "NIFTY 50", 24500.0, 0.0006, 0.008),
    ("SENSEX", "S&P BSE Sensex", 81500.0, 0.0006, 0.008),
    ("BANKNIFTY", "NIFTY Bank", 52000.0, 0.0007, 0.010),
    ("NIFTYIT", "NIFTY IT", 41000.0, 0.0004, 0.011),
    ("NIFTYMID", "NIFTY Midcap 100", 58500.0, 0.0009, 0.010),
    ("NIFTYSMALLCAP", "NIFTY Smallcap 100", 19500.0, 0.0011, 0.012),
    ("NIFTYAUTO", "NIFTY Auto", 24500.0, 0.0005, 0.010),
    ("NIFTYPHARMA", "NIFTY Pharma", 22500.0, 0.0004, 0.009),
    ("NIFTYFMCG", "NIFTY FMCG", 59000.0, 0.0003, 0.008),
    ("NIFTYMETAL", "NIFTY Metal", 9500.0, 0.0008, 0.012),
    ("NIFTYENERGY", "NIFTY Energy", 39500.0, 0.0005, 0.010),
    ("NIFTYREALTY", "NIFTY Realty", 1200.0, 0.0010, 0.014),
]

PERIOD_DAYS = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "YTD": None, "1Y": 260}

# Internal symbol -> Yahoo Finance ticker for the NSE indices
YAHOO_INDEX = {
    "NIFTY": "^NSEI",
    "SENSEX": "^BSESN",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYIT": "^CNXIT",
    "NIFTYMID": "^NSEMDCP50",
    "NIFTYSMALLCAP": "^NSESMCP50",
    "NIFTYAUTO": "^CNXAUTO",
    "NIFTYPHARMA": "^CNXPHARMA",
    "NIFTYFMCG": "^CNXFMCG",
    "NIFTYMETAL": "^CNXMETAL",
    "NIFTYENERGY": "^CNXENERGY",
    "NIFTYREALTY": "^CNXREALTY",
}


class IndexService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def seed(self, trading_days: int = 260) -> dict[str, int]:
        await self.session.execute(delete(IndexDaily))

        # Real index history from Yahoo Finance; falls back to a synthetic walk.
        real: dict[str, dict[date, tuple[float, float, float, float, int]]] = {}
        provider = None
        try:
            from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
            provider = YahooFinanceProvider()
            for symbol, *_ in INDICES:
                yahoo_ticker = YAHOO_INDEX.get(symbol)
                if not yahoo_ticker:
                    continue
                points = await provider.get_historical_prices(yahoo_ticker)
                real[symbol] = {p.trade_date: (p.open, p.high, p.low, p.close, p.volume) for p in points}
        except Exception:
            real = {}
        finally:
            if provider is not None:
                await provider.close()

        if real:
            days = sorted({d for m in real.values() for d in m})
        else:
            days = self._trading_days(trading_days)

        closes: dict[str, list[float]] = {symbol: [] for symbol, *_ in INDICES}
        added = 0

        for d in days:
            for symbol, name, base, drift, vol in INDICES:
                row = real.get(symbol, {}).get(d)
                if row is not None:
                    o, h, l, c, v = row
                    closes[symbol].append(c)
                    self.session.add(IndexDaily(
                        symbol=symbol, name=name, trade_date=d,
                        open=round(o, 2), high=round(h, 2),
                        low=round(l, 2), close=round(c, 2),
                        volume=int(v or 0),
                    ))
                    added += 1
                    continue
                if not closes[symbol]:
                    close = base * (1 + random.gauss(0, 0.002))
                else:
                    close = max(1.0, closes[symbol][-1] * (1 + drift + random.gauss(0, 1) * vol))
                closes[symbol].append(close)
                opn = closes[symbol][-2] if len(closes[symbol]) > 1 else close * (1 - drift)
                high = max(opn, close) * (1 + abs(random.gauss(0, vol * 0.4)))
                low = min(opn, close) * (1 - abs(random.gauss(0, vol * 0.4)))
                self.session.add(IndexDaily(
                    symbol=symbol, name=name, trade_date=d,
                    open=round(opn, 2), high=round(high, 2),
                    low=round(low, 2), close=round(close, 2),
                    volume=int(random.uniform(5e5, 5e6)),
                ))
                added += 1

        await self.session.flush()
        return {"indices": len(INDICES), "points": added}

    @staticmethod
    def _trading_days(days: int) -> list[date]:
        out: list[date] = []
        d = date.today()
        while len(out) < days:
            if d.weekday() < 5:
                out.append(d)
            d -= timedelta(days=1)
        out.reverse()
        return out

    async def list_all(self) -> list[dict]:
        # Try to refresh stale indices (< 5 min old is considered fresh)
        await self._refresh_stale(max_age_minutes=5)
        
        result = await self.session.execute(
            select(IndexDaily).order_by(IndexDaily.symbol, IndexDaily.trade_date.desc())
        )
        rows = result.scalars().all()
        latest: dict[str, IndexDaily] = {}
        for row in rows:
            latest.setdefault(row.symbol, row)
        items = []
        for symbol, name, *_ in INDICES:
            row = latest.get(symbol)
            if row is None:
                continue
            prev = self._prev_close(symbol, rows, row)
            change = round(row.close - prev, 2) if prev else 0.0
            change_pct = round(change / prev * 100, 2) if prev else 0.0
            items.append({
                "symbol": row.symbol,
                "name": row.name,
                "trade_date": row.trade_date.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "prev_close": prev,
                "change": change,
                "change_pct": change_pct,
                "volume": row.volume,
            })
        return items

    async def _refresh_stale(self, max_age_minutes: int = 5) -> None:
        """Fetch fresh quotes for indices whose latest row is older than max_age_minutes."""
        from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
        
        # Find indices needing refresh
        stmt = select(IndexDaily.symbol, IndexDaily.trade_date, IndexDaily.close).order_by(
            IndexDaily.symbol, IndexDaily.trade_date.desc()
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        latest: dict[str, tuple[date, float]] = {}
        for symbol, trade_date, close in rows:
            if symbol not in latest:
                latest[symbol] = (trade_date, close)
        
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=max_age_minutes)
        stale_symbols = [
            symbol for symbol, (d, _) in latest.items()
            if datetime.combine(d, datetime.min.time()) < cutoff
        ]
        
        if not stale_symbols:
            return
        
        provider = YahooFinanceProvider()
        try:
            for symbol in stale_symbols:
                yahoo_ticker = YAHOO_INDEX.get(symbol)
                if not yahoo_ticker:
                    continue
                try:
                    # Fetch latest quote (range=5d gets recent days)
                    data = await provider._get(
                        f"{provider.BASE_URL}/{yahoo_ticker}",
                        params={"range": "5d", "interval": "1d", "crumb": await provider._get_crumb()}
                    )
                    result = (data.get("chart") or {}).get("result")
                    if not result:
                        continue
                    chart = result[0]
                    timestamps = chart.get("timestamp") or []
                    quote = (chart.get("indicators") or {}).get("quote") or [{}]
                    quote = quote[0]
                    closes = quote.get("close") or []
                    if not closes:
                        continue
                    # Use the latest close
                    latest_close = closes[-1]
                    latest_ts = timestamps[-1]
                    from datetime import datetime as dt_datetime
                    trade_date = dt_datetime.fromtimestamp(
                        latest_ts, tz=datetime.now().astimezone().tzinfo
                    ).date()
                    
                    # Upsert
                    from sqlalchemy.dialects.postgresql import insert
                    from titan_x.models.index_price import IndexDaily
                    stmt = insert(IndexDaily).values(
                        symbol=symbol,
                        name=next(n for s, n, *_ in INDICES if s == symbol),
                        trade_date=trade_date,
                        open=0, high=0, low=0,
                        close=round(latest_close, 2),
                        volume=0,
                    ).on_conflict_do_update(
                        index_elements=["symbol", "trade_date"],
                        set_={"close": round(latest_close, 2)}
                    )
                    await self.session.execute(stmt)
                except Exception:
                    continue  # skip this index on error
            await self.session.flush()
        finally:
            await provider.close()

    @staticmethod
    def _prev_close(symbol: str, rows: list[IndexDaily], current: IndexDaily) -> float | None:
        for row in rows:
            if row.symbol == symbol and row.trade_date < current.trade_date:
                return row.close
        return None

    async def get_history(self, symbol: str, range_label: str = "3M") -> list[dict]:
        days = PERIOD_DAYS.get(range_label)
        stmt = select(IndexDaily).where(IndexDaily.symbol == symbol.upper())
        if days is not None:
            cutoff = date.today() - timedelta(days=int(days * 1.6))
            stmt = stmt.where(IndexDaily.trade_date >= cutoff)
        stmt = stmt.order_by(IndexDaily.trade_date.asc())
        result = await self.session.execute(stmt)
        return [
            {
                "trade_date": r.trade_date.isoformat(),
                "open": r.open, "high": r.high, "low": r.low,
                "close": r.close, "volume": r.volume,
            }
            for r in result.scalars().all()
        ]

    async def get_performance(self, symbol: str) -> dict:
        result = await self.session.execute(
            select(IndexDaily)
            .where(IndexDaily.symbol == symbol.upper())
            .order_by(IndexDaily.trade_date.desc())
        )
        rows = result.scalars().all()
        if not rows:
            return {}
        last_close = rows[0].close
        by_symbol_close = {r.trade_date: r.close for r in rows}
        periods = {}
        for label, days in PERIOD_DAYS.items():
            if days is None:
                start_of_year = date(date.today().year, 1, 1)
                start = self._closest_close(by_symbol_close, start_of_year)
            else:
                start = self._closest_close(by_symbol_close, rows[0].trade_date - timedelta(days=int(days * 1.6)))
            if start is None or start <= 0:
                periods[label] = None
            else:
                periods[label] = round((last_close - start) / start * 100, 2)
        return {
            "symbol": symbol.upper(),
            "trade_date": rows[0].trade_date.isoformat(),
            "close": last_close,
            "periods": periods,
        }

    @staticmethod
    def _closest_close(close_map: dict[date, float], target: date) -> float | None:
        closest = None
        for d in sorted(close_map.keys()):
            if d > target:
                break
            closest = d
        return close_map.get(closest) if closest else None
