import math
from collections.abc import Sequence
from datetime import date
from typing import Any


class PerformanceAnalyzer:
    def calculate_pnl(self, trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
        if not trades:
            return {
                "total_return": 0.0, "total_return_pct": 0.0,
                "total_trades": 0, "winning_trades": 0,
                "losing_trades": 0, "win_rate": 0.0,
                "profit_factor": None, "avg_win": None,
                "avg_loss": None, "avg_holding_days": None,
                "best_trade_pnl": None, "worst_trade_pnl": None,
            }

        closed = [t for t in trades if t.get("status") == "closed" and t.get("pnl") is not None]
        total_trades = len(closed)
        if total_trades == 0:
            return {
                "total_return": 0.0, "total_return_pct": 0.0,
                "total_trades": 0, "winning_trades": 0,
                "losing_trades": 0, "win_rate": 0.0,
                "profit_factor": None, "avg_win": None,
                "avg_loss": None, "avg_holding_days": None,
                "best_trade_pnl": None, "worst_trade_pnl": None,
            }

        winners = [t for t in closed if t["pnl"] > 0]
        losers = [t for t in closed if t["pnl"] <= 0]
        winning_trades = len(winners)
        losing_trades = len(losers)

        total_pnl = sum(t["pnl"] for t in closed)
        total_pnl_pct = sum(t.get("pnl_pct", 0.0) for t in closed)
        gross_profit = sum(t["pnl"] for t in winners) if winners else 0.0
        gross_loss = abs(sum(t["pnl"] for t in losers)) if losers else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
        avg_win = sum(t["pnl"] for t in winners) / winning_trades if winning_trades else None
        avg_loss = sum(t["pnl"] for t in losers) / losing_trades if losing_trades else None
        holding_days_list = [t["holding_days"] for t in closed if t.get("holding_days") is not None]
        avg_holding_days = sum(holding_days_list) / len(holding_days_list) if holding_days_list else None
        best_trade = max(closed, key=lambda t: t["pnl"])
        worst_trade = min(closed, key=lambda t: t["pnl"])

        return {
            "total_return": total_pnl,
            "total_return_pct": total_pnl_pct,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": (winning_trades / total_trades * 100) if total_trades else 0.0,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "avg_holding_days": avg_holding_days,
            "best_trade_pnl": best_trade["pnl"],
            "worst_trade_pnl": worst_trade["pnl"],
        }

    def calculate_drawdown(self, equity_curve: Sequence[dict[str, Any]]) -> dict[str, Any]:
        if not equity_curve:
            return {"max_drawdown": 0.0, "max_drawdown_pct": 0.0, "avg_drawdown": None, "avg_drawdown_pct": None}

        peak = equity_curve[0]["equity"]
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        drawdowns: list[float] = []
        drawdowns_pct: list[float] = []

        for point in equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = peak - eq
            dd_pct = ((peak - eq) / peak * 100) if peak > 0 else 0.0
            drawdowns.append(dd)
            drawdowns_pct.append(dd_pct)
            if dd > max_drawdown:
                max_drawdown = dd
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

        positive_drawdowns = [d for d in drawdowns if d > 0]
        positive_drawdowns_pct = [d for d in drawdowns_pct if d > 0]
        avg_drawdown = sum(positive_drawdowns) / len(positive_drawdowns) if positive_drawdowns else 0.0
        avg_drawdown_pct = sum(positive_drawdowns_pct) / len(positive_drawdowns_pct) if positive_drawdowns_pct else 0.0

        return {
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "avg_drawdown": avg_drawdown,
            "avg_drawdown_pct": avg_drawdown_pct,
        }

    def calculate_daily_returns(self, equity_curve: Sequence[dict[str, Any]]) -> list[float]:
        if len(equity_curve) < 2:
            return []
        returns: list[float] = []
        for i in range(1, len(equity_curve)):
            prev_eq = equity_curve[i - 1]["equity"]
            curr_eq = equity_curve[i]["equity"]
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)
        return returns

    def calculate_sharpe(self, daily_returns: list[float], risk_free_rate: float = 0.02) -> float | None:
        if len(daily_returns) < 2:
            return None
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0
        if std_dev == 0:
            return None
        daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
        return ((mean_return - daily_rf) / std_dev) * math.sqrt(252)

    def calculate_sortino(self, daily_returns: list[float], risk_free_rate: float = 0.02) -> float | None:
        if len(daily_returns) < 2:
            return None
        mean_return = sum(daily_returns) / len(daily_returns)
        downside_returns = [r for r in daily_returns if r < 0]
        if not downside_returns:
            return None
        downside_var = sum(r ** 2 for r in downside_returns) / len(daily_returns)
        downside_std = math.sqrt(downside_var) if downside_var > 0 else 0.0
        if downside_std == 0:
            return None
        daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
        return ((mean_return - daily_rf) / downside_std) * math.sqrt(252)

    def calculate_calmar(self, annualized_return_pct: float | None, max_drawdown_pct: float) -> float | None:
        if max_drawdown_pct == 0 or annualized_return_pct is None:
            return None
        return abs(annualized_return_pct / max_drawdown_pct)

    def calculate_annualized_return(
        self, starting_equity: float, ending_equity: float,
        start_date: date, end_date: date,
    ) -> float | None:
        if starting_equity <= 0:
            return None
        total_return = ending_equity / starting_equity
        days = (end_date - start_date).days
        if days <= 0:
            return None
        years = days / 365.25
        if years <= 0:
            return None
        return (total_return ** (1 / years) - 1) * 100

    def generate_equity_curve(
        self, price_dates: Sequence[date],
        price_close: Sequence[float],
        trades: Sequence[dict[str, Any]],
        initial_capital: float,
    ) -> list[dict[str, Any]]:
        """Build a mark-to-market equity curve from executed trades.

        Trade entry/exit prices are authoritative for cash movements. The supplied
        close prices are used only to mark an open position to market. This keeps
        the equity curve consistent with the actual execution model and avoids
        silently replacing execution prices with daily closes.
        """
        if initial_capital <= 0 or not price_dates:
            return []
        if len(price_dates) != len(price_close):
            raise ValueError("price_dates and price_close must have the same length")

        price_by_date = {d: float(p) for d, p in zip(price_dates, price_close)}
        ordered_dates = list(price_dates)

        valid_trades = [
            t for t in trades
            if t.get("entry_date") is not None and t.get("quantity") is not None
        ]
        valid_trades.sort(key=lambda t: (t["entry_date"], t.get("exit_date") or date.max))

        entries_by_date: dict[date, list[dict[str, Any]]] = {}
        exits_by_date: dict[date, list[dict[str, Any]]] = {}
        for trade in valid_trades:
            entries_by_date.setdefault(trade["entry_date"], []).append(trade)
            if trade.get("exit_date") is not None:
                exits_by_date.setdefault(trade["exit_date"], []).append(trade)

        cash = float(initial_capital)
        position: dict[str, Any] | None = None
        curve: list[dict[str, Any]] = []

        for current_date in ordered_dates:
            close_price = price_by_date[current_date]

            # Exits are processed before new entries on the same date.
            if position is not None:
                trade = position["trade"]
                if trade.get("exit_date") == current_date:
                    quantity = float(position["quantity"])
                    exit_price = float(trade.get("exit_price") or close_price)
                    exit_commission = float(trade.get("exit_commission", trade.get("commission_exit", 0.0)) or 0.0)
                    cash += quantity * exit_price - exit_commission
                    position = None

            if position is None:
                for trade in entries_by_date.get(current_date, []):
                    quantity = float(trade["quantity"])
                    entry_price = float(trade.get("entry_price") or close_price)
                    entry_commission = float(trade.get("entry_commission", trade.get("commission_entry", 0.0)) or 0.0)
                    required_cash = quantity * entry_price + entry_commission
                    if quantity <= 0 or required_cash > cash:
                        continue
                    cash -= required_cash
                    position = {
                        "trade": trade,
                        "quantity": quantity,
                        "entry_price": entry_price,
                    }
                    break

            holdings_value = 0.0
            if position is not None:
                holdings_value = float(position["quantity"]) * close_price

            equity = cash + holdings_value
            previous_equity = curve[-1]["equity"] if curve else initial_capital
            returns_pct = ((equity - previous_equity) / previous_equity * 100) if previous_equity > 0 else 0.0

            curve.append({
                "date": current_date,
                "equity": equity,
                "cash": cash,
                "holdings_value": holdings_value,
                "returns_pct": returns_pct,
                "drawdown_pct": 0.0,
            })

        peak = float(initial_capital)
        for point in curve:
            peak = max(peak, point["equity"])
            point["drawdown_pct"] = ((peak - point["equity"]) / peak * 100) if peak > 0 else 0.0

        return curve

    def compute_all_metrics(
        self,
        trades: Sequence[dict[str, Any]],
        equity_curve: Sequence[dict[str, Any]],
        starting_equity: float,
        ending_equity: float,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        pnl = self.calculate_pnl(trades)
        dd = self.calculate_drawdown(equity_curve)
        daily_returns = self.calculate_daily_returns(equity_curve)
        sharpe = self.calculate_sharpe(daily_returns)
        sortino = self.calculate_sortino(daily_returns)
        annualized_return = self.calculate_annualized_return(starting_equity, ending_equity, start_date, end_date)
        calmar = self.calculate_calmar(annualized_return, dd["max_drawdown_pct"])
        total_commission = sum(t.get("commission", 0.0) for t in trades)
        total_slippage = sum(t.get("slippage", 0.0) for t in trades)

        return {
            **pnl,
            **dd,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "annualized_return_pct": annualized_return,
            "starting_equity": starting_equity,
            "ending_equity": ending_equity,
            "total_commission": total_commission,
            "total_slippage": total_slippage,
        }
