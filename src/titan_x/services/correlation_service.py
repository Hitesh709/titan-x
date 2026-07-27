import json
import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.correlation import CorrelationMatrix, CorrelationPair
from titan_x.models.price import DailyPrice


class CorrelationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ============================================================
    # STOCK CORRELATION
    # ============================================================

    async def stock_correlation(
        self, symbol_a: str, symbol_b: str, lookback_days: int = 252,
    ) -> CorrelationPair:
        symbol_a, symbol_b = symbol_a.upper(), symbol_b.upper()
        as_of = date.today()
        returns_a = await self._get_returns(symbol_a, lookback_days)
        returns_b = await self._get_returns(symbol_b, lookback_days)

        common_dates = sorted(set(returns_a.keys()) & set(returns_b.keys()))
        ra = [returns_a[d] for d in common_dates]
        rb = [returns_b[d] for d in common_dates]
        corr = self._pearson(ra, rb) if len(ra) >= 5 else None

        pair = CorrelationPair(
            correlation_type="stock",
            symbol_1=symbol_a, symbol_2=symbol_b,
            correlation_value=corr,
            lookback_days=lookback_days,
            as_of_date=as_of,
            samples=len(common_dates),
        )
        self.session.add(pair)
        await self.session.flush()
        await self.session.refresh(pair)
        return pair

    # ============================================================
    # SECTOR CORRELATION
    # ============================================================

    async def sector_correlation(
        self, sector_a: str, sector_b: str, lookback_days: int = 252,
    ) -> CorrelationPair:
        as_of = date.today()
        ret_a = await self._get_sector_returns(sector_a, lookback_days)
        ret_b = await self._get_sector_returns(sector_b, lookback_days)

        common_dates = sorted(set(ret_a.keys()) & set(ret_b.keys()))
        ra = [ret_a[d] for d in common_dates]
        rb = [ret_b[d] for d in common_dates]
        corr = self._pearson(ra, rb) if len(ra) >= 5 else None

        pair = CorrelationPair(
            correlation_type="sector",
            symbol_1=sector_a, symbol_2=sector_b,
            correlation_value=corr,
            lookback_days=lookback_days,
            as_of_date=as_of,
            samples=len(common_dates),
        )
        self.session.add(pair)
        await self.session.flush()
        await self.session.refresh(pair)
        return pair

    # ============================================================
    # INDEX CORRELATION
    # ============================================================

    async def index_correlation(
        self, symbol: str, index_symbol: str = "NIFTY", lookback_days: int = 252,
    ) -> CorrelationPair:
        return await self.stock_correlation(symbol, index_symbol, lookback_days)

    # ============================================================
    # PORTFOLIO CORRELATION (full matrix)
    # ============================================================

    async def portfolio_correlation(
        self, symbols: list[str], portfolio_label: str | None = None, lookback_days: int = 252,
    ) -> CorrelationMatrix:
        as_of = date.today()
        label = portfolio_label or "+".join(sorted(symbols))
        symbols_upper = sorted(set(s.upper() for s in symbols))

        all_returns = {}
        for sym in symbols_upper:
            all_returns[sym] = await self._get_returns(sym, lookback_days)

        common_dates = sorted(set.intersection(
            *(set(r.keys()) for r in all_returns.values())
        )) if all_returns else []

        if len(common_dates) < 5:
            matrix = [[1.0 if i == j else 0.0 for j in range(len(symbols_upper))] for i in range(len(symbols_upper))]
        else:
            matrix = []
            for i in range(len(symbols_upper)):
                row = []
                for j in range(len(symbols_upper)):
                    if i == j:
                        row.append(1.0)
                    else:
                        ri = [all_returns[symbols_upper[i]][d] for d in common_dates]
                        rj = [all_returns[symbols_upper[j]][d] for d in common_dates]
                        row.append(self._pearson(ri, rj) or 0.0)
                matrix.append(row)

        result = CorrelationMatrix(
            matrix_type="portfolio",
            label=label,
            as_of_date=as_of,
            lookback_days=lookback_days,
            symbols_json=json.dumps(symbols_upper),
            matrix_json=json.dumps([[round(v, 4) for v in row] for row in matrix]),
            metadata_json=json.dumps({
                "samples": len(common_dates),
                "date_range": {
                    "start": common_dates[0].isoformat() if common_dates else None,
                    "end": common_dates[-1].isoformat() if common_dates else None,
                },
            }),
        )
        self.session.add(result)
        await self.session.flush()
        await self.session.refresh(result)
        return result

    # ============================================================
    # HEATMAP
    # ============================================================

    async def heatmap(
        self, symbols: list[str], lookback_days: int = 252,
    ) -> CorrelationMatrix:
        return await self.portfolio_correlation(symbols, "heatmap", lookback_days)

    # ============================================================
    # SECTOR HEATMAP
    # ============================================================

    async def sector_heatmap(self, lookback_days: int = 252) -> CorrelationMatrix:
        sectors_result = await self.session.execute(
            select(Company.sector).distinct().where(Company.sector.isnot(None))
        )
        sectors = sorted(set(r[0] for r in sectors_result.all()))
        if len(sectors) < 2:
            raise ValueError("Need at least 2 sectors with data")

        as_of = date.today()
        all_returns = {}
        for sec in sectors:
            all_returns[sec] = await self._get_sector_returns(sec, lookback_days)

        common_dates = sorted(set.intersection(
            *(set(r.keys()) for r in all_returns.values())
        )) if all_returns else []

        matrix = []
        for i in range(len(sectors)):
            row = []
            for j in range(len(sectors)):
                if i == j:
                    row.append(1.0)
                else:
                    ri = [all_returns[sectors[i]][d] for d in common_dates]
                    rj = [all_returns[sectors[j]][d] for d in common_dates]
                    row.append(self._pearson(ri, rj) or 0.0)
            matrix.append(row)

        result = CorrelationMatrix(
            matrix_type="sector_heatmap",
            label="sector_heatmap",
            as_of_date=as_of,
            lookback_days=lookback_days,
            symbols_json=json.dumps(sectors),
            matrix_json=json.dumps([[round(v, 4) for v in row] for row in matrix]),
            metadata_json=json.dumps({
                "samples": len(common_dates),
                "date_range": {
                    "start": common_dates[0].isoformat() if common_dates else None,
                    "end": common_dates[-1].isoformat() if common_dates else None,
                },
            }),
        )
        self.session.add(result)
        await self.session.flush()
        await self.session.refresh(result)
        return result

    # ============================================================
    # GETTERS
    # ============================================================

    async def get_pair(self, correlation_type: str, symbol_1: str, symbol_2: str) -> CorrelationPair | None:
        r = await self.session.execute(
            select(CorrelationPair).where(
                CorrelationPair.correlation_type == correlation_type,
                CorrelationPair.symbol_1 == symbol_1.upper(),
                CorrelationPair.symbol_2 == symbol_2.upper(),
            ).order_by(CorrelationPair.as_of_date.desc()).limit(1)
        )
        return r.scalar_one_or_none()

    async def get_matrix(self, matrix_type: str, label: str) -> CorrelationMatrix | None:
        r = await self.session.execute(
            select(CorrelationMatrix).where(
                CorrelationMatrix.matrix_type == matrix_type,
                CorrelationMatrix.label == label,
            ).order_by(CorrelationMatrix.as_of_date.desc()).limit(1)
        )
        return r.scalar_one_or_none()

    # ============================================================
    # PRIVATE HELPERS
    # ============================================================

    async def _get_returns(self, symbol: str, lookback_days: int) -> dict[date, float]:
        latest_r = await self.session.execute(
            select(DailyPrice.trade_date).where(DailyPrice.symbol == symbol)
            .order_by(DailyPrice.trade_date.desc()).limit(1)
        )
        latest = latest_r.scalar_one_or_none()
        if latest is None:
            return {}
        lookback = latest - timedelta(days=lookback_days + 10)
        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= lookback,
                DailyPrice.trade_date <= latest,
            ).order_by(DailyPrice.trade_date.asc())
        )
        prices = list(r.scalars().all())
        returns = {}
        for i in range(1, len(prices)):
            prev = prices[i - 1].close
            if prev > 0:
                ret = (prices[i].close - prev) / prev
                returns[prices[i].trade_date] = ret
        return returns

    async def _get_sector_returns(self, sector: str, lookback_days: int) -> dict[date, float]:
        comp_result = await self.session.execute(
            select(Company.symbol).where(Company.sector == sector)
        )
        symbols = [r[0] for r in comp_result.all()]
        if not symbols:
            return {}

        all_returns = defaultdict(list)
        for sym in symbols:
            rets = await self._get_returns(sym, lookback_days)
            for d, r_val in rets.items():
                all_returns[d].append(r_val)

        avg_returns = {}
        for d, vals in all_returns.items():
            avg_returns[d] = sum(vals) / len(vals)
        return avg_returns

    def _pearson(self, a: list[float], b: list[float]) -> float | None:
        n = len(a)
        if n < 5:
            return None
        sum_a = sum(a)
        sum_b = sum(b)
        sum_ab = sum(x * y for x, y in zip(a, b))
        sum_a2 = sum(x * x for x in a)
        sum_b2 = sum(y * y for y in b)
        num = n * sum_ab - sum_a * sum_b
        den = math.sqrt((n * sum_a2 - sum_a * sum_a) * (n * sum_b2 - sum_b * sum_b))
        if den == 0:
            return 0.0
        corr = num / den
        return max(-1.0, min(1.0, corr))
