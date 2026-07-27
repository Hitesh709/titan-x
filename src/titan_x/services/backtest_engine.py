import json
import math
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.db.repository import BaseRepository
from titan_x.models.backtest import Backtest, BacktestEquityPoint, BacktestReport, BacktestSignal, BacktestTrade
from titan_x.models.price import DailyPrice
from titan_x.services.performance_analyzer import PerformanceAnalyzer

logger = structlog.get_logger(__name__)


class BacktestEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._backtest_repo = BaseRepository(session, Backtest)
        self._trade_repo = BaseRepository(session, BacktestTrade)
        self._signal_repo = BaseRepository(session, BacktestSignal)
        self._equity_repo = BaseRepository(session, BacktestEquityPoint)
        self._report_repo = BaseRepository(session, BacktestReport)
        self._analyzer = PerformanceAnalyzer()

    async def create_backtest(
        self,
        user_id: int,
        name: str,
        symbol: str,
        start_date: date,
        end_date: date,
        initial_capital: float = 10000.0,
        strategy_type: str = "sma_crossover",
        strategy_params: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        backtest = await self._backtest_repo.create(
            user_id=user_id,
            name=name,
            description=description,
            symbol=symbol.upper(),
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            strategy_type=strategy_type,
            strategy_params_json=json.dumps(strategy_params or {}),
            config_json=json.dumps(config or {}),
            status="draft",
        )
        return self._backtest_to_dict(backtest)

    async def run_backtest(self, backtest_id: int) -> dict[str, Any]:
        backtest = await self._backtest_repo.get(backtest_id)
        if backtest is None:
            raise ValueError(f"Backtest {backtest_id} not found")

        backtest.status = "running"
        backtest.started_at = datetime.now(tz=timezone.utc)
        await self._session.flush()

        try:
            result = await self._execute_backtest(backtest)
            backtest.status = "completed"
            backtest.completed_at = datetime.now(tz=timezone.utc)
            await self._session.flush()
            return result
        except Exception as exc:
            backtest.status = "failed"
            backtest.error_message = str(exc)
            backtest.completed_at = datetime.now(tz=timezone.utc)
            await self._session.flush()
            logger.exception("backtest_execution_failed", backtest_id=backtest_id)
            raise

    async def _execute_backtest(self, backtest: Backtest) -> dict[str, Any]:
        symbol = backtest.symbol
        start = backtest.start_date
        end = backtest.end_date
        config = json.loads(backtest.config_json) if backtest.config_json else {}
        strategy_params = json.loads(backtest.strategy_params_json) if backtest.strategy_params_json else {}

        commission_pct = config.get("commission_pct", 0.001)
        slippage_pct = config.get("slippage_pct", 0.001)
        position_sizing = config.get("position_sizing", "capital_pct")
        position_value_pct = config.get("position_value_pct", 0.95)

        prices = await self._load_price_data(symbol, start, end)
        if len(prices) < 30:
            raise ValueError(f"Insufficient price data for {symbol}: {len(prices)} bars (minimum 30)")

        indicators = self._compute_indicators(prices, backtest.strategy_type, strategy_params)

        signals = self._generate_signals(prices, indicators, backtest.strategy_type, strategy_params)

        trades, equity_curve = self._simulate_trades(
            prices, signals, backtest.initial_capital,
            commission_pct, slippage_pct, position_sizing, position_value_pct,
        )

        await self._save_signals(backtest.id, signals)
        await self._save_trades(backtest.id, trades)

        price_dates = [p["date"] for p in prices]
        price_close = [p["close"] for p in prices]

        if not equity_curve:
            equity_curve = self._analyzer.generate_equity_curve(
                price_dates, price_close, trades, backtest.initial_capital,
            )

        await self._save_equity_curve(backtest.id, equity_curve)

        metrics = self._analyzer.compute_all_metrics(
            trades, equity_curve,
            backtest.initial_capital,
            equity_curve[-1]["equity"] if equity_curve else backtest.initial_capital,
            start, end,
        )

        await self._save_report(backtest.id, metrics)

        return {
            "backtest_id": backtest.id,
            "status": "completed",
            "metrics": metrics,
            "trades_count": len(trades),
            "equity_points": len(equity_curve),
        }

    async def _load_price_data(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol.upper(),
                DailyPrice.trade_date >= start,
                DailyPrice.trade_date <= end,
            )
            .order_by(DailyPrice.trade_date)
        )
        rows = result.scalars().all()
        return [
            {
                "date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]

    def _compute_indicators(self, prices: list[dict[str, Any]], strategy_type: str, params: dict[str, Any]) -> dict[str, list[float | None]]:
        closes = [p["close"] for p in prices]
        highs = [p["high"] for p in prices]
        lows = [p["low"] for p in prices]

        indicators: dict[str, list[float | None]] = {
            "sma_fast": [None] * len(prices),
            "sma_slow": [None] * len(prices),
            "rsi": [None] * len(prices),
            "bb_upper": [None] * len(prices),
            "bb_lower": [None] * len(prices),
            "bb_middle": [None] * len(prices),
            "atr": [None] * len(prices),
        }

        fast_period = params.get("fast_period", 10)
        slow_period = params.get("slow_period", 30)
        rsi_period = params.get("rsi_period", 14)
        bb_period = params.get("bb_period", 20)
        bb_std = params.get("bb_std", 2.0)
        atr_period = params.get("atr_period", 14)

        sma_fast = self._sma(closes, fast_period)
        sma_slow = self._sma(closes, slow_period)
        rsi = self._rsi(closes, rsi_period)
        bb_mid = self._sma(closes, bb_period)
        bb_upper_list: list[float | None] = []
        bb_lower_list: list[float | None] = []

        for i in range(len(closes)):
            if bb_mid[i] is not None:
                period_data = closes[max(0, i - bb_period + 1):i + 1]
                if len(period_data) >= bb_period:
                    std = math.sqrt(sum((c - bb_mid[i]) ** 2 for c in period_data) / bb_period)
                    bb_upper_list.append(bb_mid[i] + bb_std * std)
                    bb_lower_list.append(bb_mid[i] - bb_std * std)
                else:
                    bb_upper_list.append(None)
                    bb_lower_list.append(None)
            else:
                bb_upper_list.append(None)
                bb_lower_list.append(None)

        for i in range(len(prices)):
            indicators["sma_fast"][i] = sma_fast[i]
            indicators["sma_slow"][i] = sma_slow[i]
            indicators["rsi"][i] = rsi[i]
            indicators["bb_upper"][i] = bb_upper_list[i]
            indicators["bb_lower"][i] = bb_lower_list[i]
            indicators["bb_middle"][i] = bb_mid[i]

        return indicators

    def _generate_signals(
        self, prices: list[dict[str, Any]],
        indicators: dict[str, list[float | None]],
        strategy_type: str, params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []

        if strategy_type == "sma_crossover":
            signals = self._sma_crossover_signals(prices, indicators, params)
        elif strategy_type == "rsi":
            signals = self._rsi_signals(prices, indicators, params)
        elif strategy_type == "bollinger":
            signals = self._bollinger_signals(prices, indicators, params)
        elif strategy_type == "custom":
            custom_signals = params.get("signals", [])
            for s in custom_signals:
                raw_date = s.get("date")
                if isinstance(raw_date, str):
                    signal_date = date.fromisoformat(raw_date)
                else:
                    signal_date = raw_date
                signals.append({
                    "signal_date": signal_date,
                    "action": s.get("action", "buy"),
                    "price": s.get("price", 0.0),
                    "confidence": s.get("confidence", 1.0),
                    "signal_type": "custom",
                    "source": "user",
                    "metadata_json": json.dumps(s.get("metadata", {})),
                })
        else:
            signals = self._sma_crossover_signals(prices, indicators, params)

        return signals

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
        trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        cash = initial_capital
        position: dict[str, Any] | None = None
        trade_number = 0
        signal_idx = 0

        signal_by_date: dict[date, list[dict[str, Any]]] = {}
        for s in signals:
            d = s["signal_date"]
            if d not in signal_by_date:
                signal_by_date[d] = []
            signal_by_date[d].append(s)

        for i, bar in enumerate(prices):
            d = bar["date"]
            price = bar["close"]

            day_signals = signal_by_date.get(d, [])

            if position is not None:
                price_diff = price - position["entry_price"]
                pnl = price_diff * position["quantity"]
                pnl_pct = ((price - position["entry_price"]) / position["entry_price"]) * 100
                stop_loss_pct = position.get("stop_loss_pct")

                exit_reason = None
                for s in day_signals:
                    if s["action"] in ("sell", "exit"):
                        exit_reason = s.get("signal_type", "signal")
                        break

                if stop_loss_pct is not None and pnl_pct <= -abs(stop_loss_pct):
                    exit_reason = "stop_loss"

                long_tp_pct = position.get("take_profit_pct")
                if long_tp_pct is not None and pnl_pct >= abs(long_tp_pct):
                    exit_reason = "take_profit"

                if exit_reason:
                    slippage = price * slippage_pct
                    exit_price = price - slippage if exit_reason != "stop_loss" else price
                    commission = exit_price * position["quantity"] * commission_pct
                    actual_pnl = (exit_price - position["entry_price"]) * position["quantity"] - commission - position.get("commission", 0)
                    actual_pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * 100

                    cash += exit_price * position["quantity"] - commission

                    trades.append({
                        "trade_number": trade_number,
                        "symbol": position["symbol"],
                        "side": "long",
                        "status": "closed",
                        "entry_date": position["entry_date"],
                        "entry_price": position["entry_price"],
                        "entry_signal": position.get("entry_signal"),
                        "exit_date": d,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "exit_signal": next((s["signal_type"] for s in day_signals if s["action"] in ("sell", "exit")), exit_reason),
                        "quantity": position["quantity"],
                        "commission": commission + position.get("commission", 0),
                        "slippage": slippage + position.get("slippage", 0),
                        "pnl": actual_pnl,
                        "pnl_pct": actual_pnl_pct,
                        "holding_days": (d - position["entry_date"]).days,
                    })
                    trade_number += 1
                    position = None

            if position is None:
                for s in day_signals:
                    if s["action"] in ("buy", "enter"):
                        position_value = cash * position_value_pct if position_sizing == "capital_pct" else cash
                        position_value = min(position_value, cash)
                        slippage = price * slippage_pct
                        entry_price = price + slippage
                        quantity = position_value / entry_price

                        if quantity > 0 and position_value > 0:
                            commission = entry_price * quantity * commission_pct
                            cost = entry_price * quantity + commission
                            if cost <= cash:
                                cash -= cost
                                position = {
                                    "symbol": s.get("symbol", ""),
                                    "entry_date": d,
                                    "entry_price": entry_price,
                                    "quantity": quantity,
                                    "commission": commission,
                                    "slippage": slippage,
                                    "entry_signal": s.get("signal_type"),
                                    "stop_loss_pct": s.get("stop_loss_pct"),
                                    "take_profit_pct": s.get("take_profit_pct"),
                                }

            holdings_value = position["quantity"] * price if position else 0.0
            equity = cash + holdings_value

            prev_eq = equity_curve[-1]["equity"] if equity_curve else initial_capital
            ret_pct = ((equity - prev_eq) / prev_eq * 100) if prev_eq > 0 else 0.0

            equity_curve.append({
                "date": d,
                "equity": equity,
                "cash": cash,
                "holdings_value": holdings_value,
                "returns_pct": ret_pct,
                "drawdown_pct": None,
            })

        if position is not None:
            last_price = prices[-1]["close"]
            pnl = (last_price - position["entry_price"]) * position["quantity"]
            pnl_pct = ((last_price - position["entry_price"]) / position["entry_price"]) * 100
            trades.append({
                "trade_number": trade_number,
                "symbol": position["symbol"],
                "side": "long",
                "status": "open",
                "entry_date": position["entry_date"],
                "entry_price": position["entry_price"],
                "entry_signal": position.get("entry_signal"),
                "exit_date": None,
                "exit_price": None,
                "exit_reason": "end_of_backtest",
                "exit_signal": None,
                "quantity": position["quantity"],
                "commission": position.get("commission", 0),
                "slippage": position.get("slippage", 0),
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "holding_days": (prices[-1]["date"] - position["entry_date"]).days if prices else 0,
            })

        peak = initial_capital
        for point in equity_curve:
            if point["equity"] > peak:
                peak = point["equity"]
            point["drawdown_pct"] = ((peak - point["equity"]) / peak * 100) if peak > 0 else 0.0

        return trades, equity_curve

    async def _save_signals(self, backtest_id: int, signals: list[dict[str, Any]]) -> None:
        for s in signals:
            await self._signal_repo.create(
                backtest_id=backtest_id,
                trade_id=None,
                signal_date=s["signal_date"],
                symbol=s.get("symbol", ""),
                action=s["action"],
                price=s["price"],
                confidence=s.get("confidence"),
                signal_type=s.get("signal_type", "unknown"),
                source=s.get("source", "engine"),
                metadata_json=s.get("metadata_json"),
            )

    async def _save_trades(self, backtest_id: int, trades: list[dict[str, Any]]) -> None:
        for t in trades:
            await self._trade_repo.create(
                backtest_id=backtest_id,
                trade_number=t.get("trade_number", 0),
                symbol=t.get("symbol", ""),
                side=t.get("side", "long"),
                status=t.get("status", "open"),
                entry_date=t.get("entry_date"),
                entry_price=t.get("entry_price", 0.0),
                entry_signal=t.get("entry_signal"),
                exit_date=t.get("exit_date"),
                exit_price=t.get("exit_price"),
                exit_reason=t.get("exit_reason"),
                exit_signal=t.get("exit_signal"),
                quantity=t.get("quantity", 0.0),
                commission=t.get("commission", 0.0),
                slippage=t.get("slippage", 0.0),
                pnl=t.get("pnl"),
                pnl_pct=t.get("pnl_pct"),
                holding_days=t.get("holding_days"),
            )

    async def _save_equity_curve(self, backtest_id: int, curve: list[dict[str, Any]]) -> None:
        for point in curve:
            await self._equity_repo.create(
                backtest_id=backtest_id,
                date=point["date"],
                equity=point["equity"],
                cash=point["cash"],
                holdings_value=point["holdings_value"],
                returns_pct=point.get("returns_pct"),
                drawdown_pct=point.get("drawdown_pct"),
            )

    async def _save_report(self, backtest_id: int, metrics: dict[str, Any]) -> None:
        await self._report_repo.create(
            backtest_id=backtest_id,
            total_return=metrics.get("total_return", 0.0),
            total_return_pct=metrics.get("total_return_pct", 0.0),
            annualized_return_pct=metrics.get("annualized_return_pct"),
            total_trades=metrics.get("total_trades", 0),
            winning_trades=metrics.get("winning_trades", 0),
            losing_trades=metrics.get("losing_trades", 0),
            win_rate=metrics.get("win_rate", 0.0),
            profit_factor=metrics.get("profit_factor"),
            max_drawdown=metrics.get("max_drawdown", 0.0),
            max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
            avg_drawdown=metrics.get("avg_drawdown"),
            avg_drawdown_pct=metrics.get("avg_drawdown_pct"),
            sharpe_ratio=metrics.get("sharpe_ratio"),
            sortino_ratio=metrics.get("sortino_ratio"),
            calmar_ratio=metrics.get("calmar_ratio"),
            avg_win=metrics.get("avg_win"),
            avg_loss=metrics.get("avg_loss"),
            avg_holding_days=metrics.get("avg_holding_days"),
            best_trade_pnl=metrics.get("best_trade_pnl"),
            worst_trade_pnl=metrics.get("worst_trade_pnl"),
            starting_equity=metrics.get("starting_equity", 0.0),
            ending_equity=metrics.get("ending_equity", 0.0),
            total_commission=metrics.get("total_commission", 0.0),
            total_slippage=metrics.get("total_slippage", 0.0),
            metrics_json=json.dumps(metrics),
        )

    async def get_backtest(self, backtest_id: int) -> dict[str, Any] | None:
        backtest = await self._backtest_repo.get(backtest_id)
        if backtest is None:
            return None
        return self._backtest_to_dict(backtest)

    async def get_backtest_with_report(self, backtest_id: int) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Backtest)
            .options(selectinload(Backtest.report))
            .where(Backtest.id == backtest_id)
        )
        backtest = result.unique().scalar_one_or_none()
        if backtest is None:
            return None

        report = None
        if backtest.report:
            report = self._report_to_dict(backtest.report)

        return {
            **self._backtest_to_dict(backtest),
            "report": report,
        }

    async def list_backtests(
        self, user_id: int | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[Backtest], int]:
        count_query = select(func.count()).select_from(Backtest)
        query = select(Backtest).order_by(desc(Backtest.created_at))

        if user_id is not None:
            query = query.where(Backtest.user_id == user_id)
            count_query = count_query.where(Backtest.user_id == user_id)

        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def get_trades(self, backtest_id: int) -> Sequence[BacktestTrade]:
        result = await self._session.execute(
            select(BacktestTrade)
            .where(BacktestTrade.backtest_id == backtest_id)
            .order_by(BacktestTrade.trade_number)
        )
        return result.scalars().all()

    async def get_equity_curve(self, backtest_id: int) -> Sequence[BacktestEquityPoint]:
        result = await self._session.execute(
            select(BacktestEquityPoint)
            .where(BacktestEquityPoint.backtest_id == backtest_id)
            .order_by(BacktestEquityPoint.date)
        )
        return result.scalars().all()

    async def get_signals(self, backtest_id: int) -> Sequence[BacktestSignal]:
        result = await self._session.execute(
            select(BacktestSignal)
            .where(BacktestSignal.backtest_id == backtest_id)
            .order_by(BacktestSignal.signal_date)
        )
        return result.scalars().all()

    async def delete_backtest(self, backtest_id: int) -> bool:
        return await self._backtest_repo.delete(backtest_id)

    def _sma(self, data: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * len(data)
        if len(data) < period:
            return result
        for i in range(period - 1, len(data)):
            result[i] = sum(data[i - period + 1:i + 1]) / period
        return result

    def _rsi(self, data: list[float], period: int = 14) -> list[float | None]:
        result: list[float | None] = [None] * len(data)
        if len(data) < period + 1:
            return result

        gains: list[float] = []
        losses: list[float] = []
        for i in range(1, period + 1):
            diff = data[i] - data[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        for i in range(period, len(data)):
            if avg_loss == 0:
                result[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i] = 100.0 - (100.0 / (1.0 + rs))

            if i < len(data) - 1:
                diff = data[i + 1] - data[i]
                gain = max(diff, 0)
                loss = max(-diff, 0)
                avg_gain = (avg_gain * (period - 1) + gain) / period
                avg_loss = (avg_loss * (period - 1) + loss) / period

        return result

    def _sma_crossover_signals(
        self, prices: list[dict[str, Any]],
        indicators: dict[str, list[float | None]],
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        fast = indicators["sma_fast"]
        slow = indicators["sma_slow"]

        for i in range(1, len(prices)):
            if fast[i] is None or slow[i] is None or fast[i - 1] is None or slow[i - 1] is None:
                continue

            if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
                stop_loss = params.get("stop_loss_pct", 5.0)
                take_profit = params.get("take_profit_pct", 10.0)
                signals.append({
                    "signal_date": prices[i]["date"],
                    "action": "buy",
                    "price": prices[i]["close"],
                    "confidence": 1.0,
                    "signal_type": "sma_crossover_buy",
                    "source": "sma_crossover",
                    "stop_loss_pct": stop_loss,
                    "take_profit_pct": take_profit,
                    "metadata_json": json.dumps({
                        "fast_sma": fast[i], "slow_sma": slow[i],
                    }),
                })

            elif fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
                signals.append({
                    "signal_date": prices[i]["date"],
                    "action": "sell",
                    "price": prices[i]["close"],
                    "confidence": 1.0,
                    "signal_type": "sma_crossover_sell",
                    "source": "sma_crossover",
                    "metadata_json": json.dumps({
                        "fast_sma": fast[i], "slow_sma": slow[i],
                    }),
                })

        return signals

    def _rsi_signals(
        self, prices: list[dict[str, Any]],
        indicators: dict[str, list[float | None]],
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        rsi = indicators["rsi"]
        oversold = params.get("oversold", 30)
        overbought = params.get("overbought", 70)
        stop_loss = params.get("stop_loss_pct", 5.0)
        take_profit = params.get("take_profit_pct", 10.0)

        for i in range(1, len(prices)):
            if rsi[i] is None or rsi[i - 1] is None:
                continue

            if rsi[i - 1] <= oversold and rsi[i] > oversold:
                signals.append({
                    "signal_date": prices[i]["date"],
                    "action": "buy",
                    "price": prices[i]["close"],
                    "confidence": 1.0,
                    "signal_type": "rsi_oversold_buy",
                    "source": "rsi",
                    "stop_loss_pct": stop_loss,
                    "take_profit_pct": take_profit,
                    "metadata_json": json.dumps({"rsi": rsi[i]}),
                })

            elif rsi[i - 1] >= overbought and rsi[i] < overbought:
                signals.append({
                    "signal_date": prices[i]["date"],
                    "action": "sell",
                    "price": prices[i]["close"],
                    "confidence": 1.0,
                    "signal_type": "rsi_overbought_sell",
                    "source": "rsi",
                    "metadata_json": json.dumps({"rsi": rsi[i]}),
                })

        return signals

    def _bollinger_signals(
        self, prices: list[dict[str, Any]],
        indicators: dict[str, list[float | None]],
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        upper = indicators["bb_upper"]
        lower = indicators["bb_lower"]
        stop_loss = params.get("stop_loss_pct", 5.0)
        take_profit = params.get("take_profit_pct", 10.0)

        for i in range(1, len(prices)):
            if lower[i] is None or upper[i] is None or lower[i - 1] is None:
                continue
            prev_close = prices[i - 1]["close"]
            curr_close = prices[i]["close"]

            if prev_close >= lower[i - 1] and curr_close < lower[i]:
                signals.append({
                    "signal_date": prices[i]["date"],
                    "action": "buy",
                    "price": prices[i]["close"],
                    "confidence": 1.0,
                    "signal_type": "bollinger_lower_buy",
                    "source": "bollinger",
                    "stop_loss_pct": stop_loss,
                    "take_profit_pct": take_profit,
                    "metadata_json": json.dumps({
                        "bb_lower": lower[i], "bb_upper": upper[i],
                    }),
                })

            elif prev_close <= upper[i - 1] and curr_close > upper[i]:
                signals.append({
                    "signal_date": prices[i]["date"],
                    "action": "sell",
                    "price": prices[i]["close"],
                    "confidence": 1.0,
                    "signal_type": "bollinger_upper_sell",
                    "source": "bollinger",
                    "metadata_json": json.dumps({
                        "bb_lower": lower[i], "bb_upper": upper[i],
                    }),
                })

        return signals

    def _backtest_to_dict(self, bt: Backtest) -> dict[str, Any]:
        return {
            "id": bt.id,
            "user_id": bt.user_id,
            "name": bt.name,
            "description": bt.description,
            "symbol": bt.symbol,
            "start_date": bt.start_date.isoformat() if bt.start_date else None,
            "end_date": bt.end_date.isoformat() if bt.end_date else None,
            "initial_capital": bt.initial_capital,
            "strategy_type": bt.strategy_type,
            "strategy_params_json": bt.strategy_params_json,
            "config_json": bt.config_json,
            "status": bt.status,
            "started_at": bt.started_at.isoformat() if bt.started_at else None,
            "completed_at": bt.completed_at.isoformat() if bt.completed_at else None,
            "error_message": bt.error_message,
            "created_at": bt.created_at.isoformat() if bt.created_at else None,
            "updated_at": bt.updated_at.isoformat() if bt.updated_at else None,
        }

    def _report_to_dict(self, report: BacktestReport) -> dict[str, Any]:
        return {
            "total_return": report.total_return,
            "total_return_pct": report.total_return_pct,
            "annualized_return_pct": report.annualized_return_pct,
            "total_trades": report.total_trades,
            "winning_trades": report.winning_trades,
            "losing_trades": report.losing_trades,
            "win_rate": report.win_rate,
            "profit_factor": report.profit_factor,
            "max_drawdown": report.max_drawdown,
            "max_drawdown_pct": report.max_drawdown_pct,
            "avg_drawdown": report.avg_drawdown,
            "avg_drawdown_pct": report.avg_drawdown_pct,
            "sharpe_ratio": report.sharpe_ratio,
            "sortino_ratio": report.sortino_ratio,
            "calmar_ratio": report.calmar_ratio,
            "avg_win": report.avg_win,
            "avg_loss": report.avg_loss,
            "avg_holding_days": report.avg_holding_days,
            "best_trade_pnl": report.best_trade_pnl,
            "worst_trade_pnl": report.worst_trade_pnl,
            "starting_equity": report.starting_equity,
            "ending_equity": report.ending_equity,
            "total_commission": report.total_commission,
            "total_slippage": report.total_slippage,
            "metrics_json": report.metrics_json,
        }
