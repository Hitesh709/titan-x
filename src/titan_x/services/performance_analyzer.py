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

        for point in equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = peak - eq
            dd_pct = ((peak - eq) / peak * 100) if peak > 0 else 0.0
            drawdowns.append(dd_pct)
            if dd > max_drawdown:
                max_drawdown = dd
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

        positive_drawdowns = [d for d in drawdowns if d > 0]
        avg_drawdown = sum(positive_drawdowns) / len(positive_drawdowns) if positive_drawdowns else 0.0
        avg_drawdown_pct = avg_drawdown

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
                r = (curr_eq - prev_eq) / prev_eq
                returns.append(r)

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
        excess_returns = mean_return - daily_rf
        annualized = (excess_returns / std_dev) * math.sqrt(252)
        return annualized

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
        excess_returns = mean_return - daily_rf
        annualized = (excess_returns / downside_std) * math.sqrt(252)
        return annualized

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
        annualized = (total_return ** (1 / years) - 1) * 100
        return annualized

    def generate_equity_curve(
        self, price_dates: Sequence[date],
        price_close: Sequence[float],
        trades: Sequence[dict[str, Any]],
        initial_capital: float,
    ) -> list[dict[str, Any]]:
        curve: list[dict[str, Any]] = []
        cash = initial_capital
        position: dict[str, Any] = {"active": False, "quantity": 0.0, "entry_price": 0.0}

        price_by_date: dict[date, float] = {}
        for d, p in zip(price_dates, price_close):
            price_by_date[d] = p

        trade_entries = {(t["entry_date"], t["symbol"]): t for t in trades if t.get("entry_date")}
        trade_exits = {(t.get("exit_date"), t["symbol"]): t for t in trades if t.get("exit_date")}

        running_trades: list[dict[str, Any]] = []

        for i, d in enumerate(price_dates):
            if d in price_by_date:
                price = price_by_date[d]

                entry_key = (d, "")
                for t in trade_entries:
                    if t[0] == d:
                        entry_key = t
                        break

                if entry_key in trade_entries and not position["active"]:
                    t = trade_entries[entry_key]
                    pos_quantity = t["quantity"]
                    cost = pos_quantity * price
                    if cost <= cash:
                        cash -= cost
                        position = {"active": True, "quantity": pos_quantity, "entry_price": price}
                        running_trades.append(position)

                holdings_value = position["quantity"] * price if position["active"] else 0.0
                equity = cash + holdings_value

                exit_key = (d, "")
                for t in trade_exits:
                    if t[0] == d:
                        exit_key = t
                        break

                if exit_key in trade_exits and position["active"]:
                    t = trade_exits[exit_key]
                    cash += t.get("exit_price", price) * position["quantity"]
                    position = {"active": False, "quantity": 0.0, "entry_price": 0.0}
                    holdings_value = 0.0
                    equity = cash

                prev_eq = curve[-1]["equity"] if curve else initial_capital
                ret_pct = ((equity - prev_eq) / prev_eq * 100) if prev_eq > 0 else 0.0

                curve.append({
                    "date": d,
                    "equity": equity,
                    "cash": cash,
                    "holdings_value": holdings_value,
                    "returns_pct": ret_pct,
                    "drawdown_pct": None,
                })

        peak = initial_capital
        for point in curve:
            if point["equity"] > peak:
                peak = point["equity"]
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
