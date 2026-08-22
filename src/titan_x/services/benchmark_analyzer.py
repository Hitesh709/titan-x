from __future__ import annotations

from datetime import date
from typing import Any, Sequence


class BenchmarkAnalyzer:
    """Compare a backtest equity curve with a benchmark price series."""

    def compare(
        self,
        equity_curve: Sequence[dict[str, Any]],
        benchmark_dates: Sequence[date],
        benchmark_close: Sequence[float],
        starting_equity: float,
    ) -> dict[str, Any]:
        if starting_equity <= 0:
            raise ValueError("starting_equity must be positive")
        if len(benchmark_dates) != len(benchmark_close):
            raise ValueError("benchmark_dates and benchmark_close must have the same length")
        if not equity_curve or not benchmark_dates:
            return {
                "strategy_return_pct": 0.0,
                "benchmark_return_pct": 0.0,
                "alpha_pct": 0.0,
                "benchmark_start": None,
                "benchmark_end": None,
            }

        prices = [(d, float(p)) for d, p in zip(benchmark_dates, benchmark_close)]
        prices = [(d, p) for d, p in prices if p > 0]
        if not prices:
            raise ValueError("benchmark must contain at least one positive price")

        strategy_start = float(equity_curve[0]["equity"])
        strategy_end = float(equity_curve[-1]["equity"])
        benchmark_start = prices[0][1]
        benchmark_end = prices[-1][1]

        strategy_return = (strategy_end / strategy_start - 1.0) * 100 if strategy_start > 0 else 0.0
        benchmark_return = (benchmark_end / benchmark_start - 1.0) * 100

        return {
            "strategy_return_pct": strategy_return,
            "benchmark_return_pct": benchmark_return,
            "alpha_pct": strategy_return - benchmark_return,
            "benchmark_start": benchmark_start,
            "benchmark_end": benchmark_end,
        }
