from __future__ import annotations

from math import sqrt
from typing import Any, Sequence


class AnalyticsDashboardService:
    """Builds a frontend-ready analytics snapshot from equity/trade series."""

    def build(self, equity: Sequence[float], trades: Sequence[float], benchmark_return_pct: float | None = None) -> dict[str, Any]:
        if not equity:
            raise ValueError("equity series cannot be empty")
        values = [float(x) for x in equity]
        trade_pnl = [float(x) for x in trades]
        initial = values[0]
        final = values[-1]
        total_return = ((final / initial) - 1) * 100 if initial else 0.0
        peak = values[0]
        drawdowns = []
        for value in values:
            peak = max(peak, value)
            drawdowns.append((value / peak - 1) * 100 if peak else 0.0)
        max_drawdown = min(drawdowns)
        wins = [x for x in trade_pnl if x > 0]
        losses = [x for x in trade_pnl if x < 0]
        win_rate = len(wins) / len(trade_pnl) * 100 if trade_pnl else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
        returns = [(values[i] / values[i - 1] - 1) for i in range(1, len(values)) if values[i - 1]]
        mean = sum(returns) / len(returns) if returns else 0.0
        variance = sum((r - mean) ** 2 for r in returns) / len(returns) if returns else 0.0
        std = sqrt(variance)
        sharpe = mean / std * sqrt(252) if std else 0.0
        downside = [min(0.0, r) for r in returns]
        downside_dev = sqrt(sum(r * r for r in downside) / len(downside)) if downside else 0.0
        sortino = mean / downside_dev * sqrt(252) if downside_dev else 0.0
        alpha = total_return - benchmark_return_pct if benchmark_return_pct is not None else None
        monthly = {f"period_{i + 1}": round((values[i] / values[i - 1] - 1) * 100, 4) for i in range(1, len(values))}
        return {
            "summary": {"initial_equity": initial, "final_equity": final, "total_return_pct": round(total_return, 4), "max_drawdown_pct": round(max_drawdown, 4)},
            "risk": {"sharpe": round(sharpe, 4), "sortino": round(sortino, 4), "profit_factor": profit_factor},
            "trades": {"count": len(trade_pnl), "win_rate_pct": round(win_rate, 4), "best_trade": max(trade_pnl) if trade_pnl else None, "worst_trade": min(trade_pnl) if trade_pnl else None},
            "benchmark": {"return_pct": benchmark_return_pct, "alpha_pct": round(alpha, 4) if alpha is not None else None},
            "equity_curve": values,
            "drawdown_curve": [round(x, 4) for x in drawdowns],
            "period_returns": monthly,
        }
