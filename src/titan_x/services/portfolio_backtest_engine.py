from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PortfolioBacktestPoint:
    date: date
    equity: float
    cash: float
    holdings_value: float
    return_pct: float
    drawdown_pct: float


class PortfolioBacktestEngine:
    """Deterministic multi-asset buy-and-hold portfolio backtester.

    Prices are supplied as {symbol: [(date, close), ...]}. Allocations are
    normalized to 100%. Capital is invested on the first common trading date
    and subsequently marked to market. This is intentionally separate from
    the live PortfolioEngine so historical simulation cannot mutate holdings.
    """

    def run(
        self,
        prices: Mapping[str, Sequence[tuple[date, float]]],
        allocations: Mapping[str, float],
        initial_capital: float,
        *,
        commission_bps: float = 0.0,
        slippage_bps: float = 0.0,
    ) -> dict:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if not prices or not allocations:
            raise ValueError("prices and allocations are required")
        if commission_bps < 0 or slippage_bps < 0:
            raise ValueError("cost parameters cannot be negative")

        symbols = [s for s in allocations if s in prices]
        if not symbols:
            raise ValueError("no allocated symbols have price data")
        total_weight = sum(float(allocations[s]) for s in symbols)
        if total_weight <= 0:
            raise ValueError("allocation weights must be positive")
        weights = {s: float(allocations[s]) / total_weight for s in symbols}

        series = {}
        for symbol in symbols:
            rows = sorted(prices[symbol], key=lambda x: x[0])
            if not rows or any(p <= 0 for _, p in rows):
                raise ValueError(f"invalid prices for {symbol}")
            series[symbol] = dict(rows)

        common_dates = sorted(set.intersection(*(set(v) for v in series.values())))
        if len(common_dates) < 2:
            raise ValueError("at least two common trading dates are required")

        first = common_dates[0]
        effective_cost = (commission_bps + slippage_bps) / 10000.0
        invested = initial_capital
        initial_cost = invested * effective_cost
        invested_after_cost = invested - initial_cost
        shares = {
            s: (invested_after_cost * weights[s]) / series[s][first]
            for s in symbols
        }
        cash = initial_cost * 0.0
        peak = initial_capital
        points: list[PortfolioBacktestPoint] = []

        for d in common_dates:
            holdings_value = sum(shares[s] * series[s][d] for s in symbols)
            equity = cash + holdings_value
            peak = max(peak, equity)
            drawdown = ((equity / peak) - 1.0) * 100.0 if peak else 0.0
            ret = ((equity / initial_capital) - 1.0) * 100.0
            points.append(PortfolioBacktestPoint(d, equity, cash, holdings_value, ret, drawdown))

        final_equity = points[-1].equity
        total_return_pct = ((final_equity / initial_capital) - 1.0) * 100.0
        max_drawdown_pct = min(p.drawdown_pct for p in points)
        return {
            "initial_capital": initial_capital,
            "ending_equity": round(final_equity, 2),
            "total_return": round(final_equity - initial_capital, 2),
            "total_return_pct": round(total_return_pct, 4),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
            "symbols": symbols,
            "allocations": {s: round(weights[s] * 100, 4) for s in symbols},
            "commission_bps": commission_bps,
            "slippage_bps": slippage_bps,
            "equity_curve": [asdict(p) for p in points],
        }
