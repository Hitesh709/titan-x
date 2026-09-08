import random
import time
from datetime import date, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.index_price import IndexDaily

logger = structlog.get_logger(__name__)

# Per-process throttle: true once every max_age_minutes at most.
_last_refresh_attempt: float | None = None

# (symbol, name, base, drift_pct, volatility_pct)
INDICES = [
    ("NIFTY", "NIFTY 50", 25000.0, 0.0006, 0.008),
    ("SENSEX", "S&P BSE Sensex", 82000.0, 0.0006, 0.008),
    ("BANKNIFTY", "NIFTY Bank", 53000.0, 0.0007, 0.010),
    ("NIFTYIT", "NIFTY IT", 42000.0, 0.0004, 0.011),
    ("NIFTYMID", "NIFTY Midcap 100", 59500.0, 0.0009, 0.010),
    ("NIFTYSMALLCAP", "NIFTY Smallcap 100", 20000.0, 0.0011, 0.012),
    ("NIFTYAUTO", "NIFTY Auto", 25000.0, 0.0005, 0.010),
    ("NIFTYPHARMA", "NIFTY Pharma", 23000.0, 0.0004, 0.009),
    ("NIFTYFMCG", "NIFTY FMCG", 60000.0, 0.0003, 0.008),
    ("NIFTYMETAL", "NIFTY Metal", 9800.0, 0.0008, 0.012),
    ("NIFTYENERGY", "NIFTY Energy", 40000.0, 0.0005, 0.010),
    ("NIFTYREALTY", "NIFTY Realty", 1250.0, 0.0010, 0.014),
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
        # Best-effort intraday refresh, throttled to once per 5 minutes so a
        # blocked/slow upstream never stalls or hammers every request.
        try:
            await self._refresh_stale(max_age_minutes=5)
        except Exception:  # noqa: BLE001
            # Refresh is best-effort; serve whatever is stored.
            logger.warning("index_refresh_failed", error="unexpected", exc_info=True)
        
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
        """Ensure the latest index rows are at most max_age_minutes old.

        Uses a per-process throttle (not a DB timestamp) so the app never
        hammers Yahoo — at most one refresh attempt per max_age_minutes. When
        the market is open, ``get_quote`` returns the live regular-market
        price; when closed it returns the latest EOD value.
        """
        global _last_refresh_attempt

        now = time.monotonic()
        if _last_refresh_attempt is not None and now - _last_refresh_attempt < max_age_minutes * 60:
            return

        from titan_x.infrastructure.market_data_providers import YahooFinanceProvider

        provider = YahooFinanceProvider()
        updated = 0
        errors: list[str] = []
        try:
            for symbol, name, *_ in INDICES:
                yahoo_ticker = YAHOO_INDEX.get(symbol)
                if not yahoo_ticker:
                    continue
                try:
                    quote = await provider.get_quote(yahoo_ticker)
                    last_price = quote.get("last_price")
                    if last_price is None:
                        raise ValueError(f"no regularMarketPrice ({quote.get('symbol')})")
                    trade_date = date.today()
                    existing = await self.session.execute(
                        select(IndexDaily).where(
                            IndexDaily.symbol == symbol,
                            IndexDaily.trade_date == trade_date,
                        )
                    )
                    row = existing.scalar_one_or_none()
                    if row is None:
                        row = IndexDaily(
                            symbol=symbol,
                            name=name,
                            trade_date=trade_date,
                            open=0.0, high=0.0, low=0.0, close=0.0, volume=0,
                        )
                        self.session.add(row)
                    row.close = round(float(last_price), 2)
                    prev_close = quote.get("prev_close")
                    if prev_close and not row.open:
                        row.open = round(float(prev_close), 2)
                    updated += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{symbol}: {exc}")
            if updated:
                await self.session.flush()
        finally:
            await provider.close()

        # Throttle regardless of outcome so a blocked upstream retries at most
        # once per window instead of on every /indices request.
        _last_refresh_attempt = time.monotonic()
        if errors:
            logger.warning("index_refresh_partial", updated=updated, errors=errors)
        else:
            logger.info("index_refresh_ok", updated=updated)

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
