from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.services.backtest_engine import BacktestEngine


class ProductionBacktestEngine(BacktestEngine):
    """Backtest engine with next-bar execution and realistic trade handling."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    def _simulate_trades(
        self,
        prices: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        initial_capital: float,
        commission_pct: float,
        slippage_pct: float,
        position_sizing: str,
        position_value_pct: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Simulate long-only trades using the next trading bar for signals.

        A signal generated after a bar close is never executed on that same
        close. BUY/SELL signals are scheduled for the next available bar open.
        Stop-loss/take-profit checks use the current bar's range and account
        for gaps. Open positions are closed at the final bar for a complete
        period return.
        """
        trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        cash = float(initial_capital)
        position: dict[str, Any] | None = None
        trade_number = 0

        date_to_index = {bar["date"]: i for i, bar in enumerate(prices)}
        scheduled: dict[int, list[dict[str, Any]]] = {}
        for signal in signals:
            signal_index = date_to_index.get(signal.get("signal_date"))
            if signal_index is None:
                continue
            execution_index = signal_index + 1
            if execution_index < len(prices):
                scheduled.setdefault(execution_index, []).append(signal)

        def execute_price(raw_price: float, side: str) -> tuple[float, float]:
            slip = raw_price * slippage_pct
            if side == "buy":
                return raw_price + slip, slip
            return raw_price - slip, slip

        def close_position(
            bar: dict[str, Any],
            raw_price: float,
            reason: str,
            exit_signal: str | None = None,
        ) -> None:
            nonlocal cash, position, trade_number
            if position is None:
                return

            exit_price, slippage = execute_price(raw_price, "sell")
            commission = exit_price * position["quantity"] * commission_pct
            gross_pnl = (exit_price - position["entry_price"]) * position["quantity"]
            actual_pnl = gross_pnl - commission - position.get("commission", 0.0)
            pnl_pct = (
                (exit_price - position["entry_price"]) / position["entry_price"] * 100
                if position["entry_price"] > 0
                else 0.0
            )

            cash += exit_price * position["quantity"] - commission
            trades.append({
                "trade_number": trade_number,
                "symbol": position["symbol"],
                "side": "long",
                "status": "closed",
                "entry_date": position["entry_date"],
                "entry_price": position["entry_price"],
                "entry_signal": position.get("entry_signal"),
                "exit_date": bar["date"],
                "exit_price": exit_price,
                "exit_reason": reason,
                "exit_signal": exit_signal or reason,
                "quantity": position["quantity"],
                "commission": commission + position.get("commission", 0.0),
                "slippage": slippage + position.get("slippage", 0.0),
                "pnl": actual_pnl,
                "pnl_pct": pnl_pct,
                "holding_days": (bar["date"] - position["entry_date"]).days,
            })
            trade_number += 1
            position = None

        for i, bar in enumerate(prices):
            d = bar["date"]
            open_price = float(bar["open"] or bar["close"])
            high_price = float(bar["high"] or open_price)
            low_price = float(bar["low"] or open_price)
            close_price = float(bar["close"])

            if position is not None:
                entry = position["entry_price"]
                stop_pct = position.get("stop_loss_pct")
                target_pct = position.get("take_profit_pct")
                stop_price = entry * (1 - abs(stop_pct) / 100) if stop_pct else None
                target_price = entry * (1 + abs(target_pct) / 100) if target_pct else None

                if stop_price is not None and (open_price <= stop_price or low_price <= stop_price):
                    raw_exit = open_price if open_price <= stop_price else stop_price
                    close_position(bar, raw_exit, "stop_loss")
                elif target_price is not None and (open_price >= target_price or high_price >= target_price):
                    raw_exit = open_price if open_price >= target_price else target_price
                    close_position(bar, raw_exit, "take_profit")

            day_signals = scheduled.get(i, [])
            if position is not None:
                sell_signal = next(
                    (s for s in day_signals if s.get("action") in ("sell", "exit")),
                    None,
                )
                if sell_signal is not None:
                    close_position(
                        bar,
                        open_price,
                        "signal",
                        sell_signal.get("signal_type"),
                    )

            if position is None:
                buy_signal = next(
                    (s for s in day_signals if s.get("action") in ("buy", "enter")),
                    None,
                )
                if buy_signal is not None:
                    position_value = (
                        cash * position_value_pct
                        if position_sizing == "capital_pct"
                        else cash
                    )
                    position_value = min(position_value, cash)
                    entry_price, entry_slippage = execute_price(open_price, "buy")
                    quantity = position_value / entry_price if entry_price > 0 else 0.0
                    commission = entry_price * quantity * commission_pct
                    cost = entry_price * quantity + commission
                    if quantity > 0 and cost <= cash:
                        cash -= cost
                        position = {
                            "symbol": buy_signal.get("symbol", ""),
                            "entry_date": d,
                            "entry_price": entry_price,
                            "quantity": quantity,
                            "commission": commission,
                            "slippage": entry_slippage,
                            "entry_signal": buy_signal.get("signal_type"),
                            "stop_loss_pct": buy_signal.get("stop_loss_pct"),
                            "take_profit_pct": buy_signal.get("take_profit_pct"),
                        }

            holdings_value = position["quantity"] * close_price if position else 0.0
            equity = cash + holdings_value
            previous_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
            returns_pct = (
                (equity - previous_equity) / previous_equity * 100
                if previous_equity > 0
                else 0.0
            )
            equity_curve.append({
                "date": d,
                "equity": equity,
                "cash": cash,
                "holdings_value": holdings_value,
                "returns_pct": returns_pct,
                "drawdown_pct": None,
            })

        if position is not None and prices:
            close_position(prices[-1], float(prices[-1]["close"]), "end_of_backtest")
            equity_curve[-1]["cash"] = cash
            equity_curve[-1]["holdings_value"] = 0.0
            equity_curve[-1]["equity"] = cash
            previous_equity = equity_curve[-2]["equity"] if len(equity_curve) > 1 else initial_capital
            equity_curve[-1]["returns_pct"] = (
                (cash - previous_equity) / previous_equity * 100
                if previous_equity > 0 else 0.0
            )

        peak = float(initial_capital)
        for point in equity_curve:
            peak = max(peak, float(point["equity"]))
            point["drawdown_pct"] = (
                (peak - point["equity"]) / peak * 100 if peak > 0 else 0.0
            )

        return trades, equity_curve
