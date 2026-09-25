from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.historical_data_validator import HistoricalDataValidator
from titan_x.services.optimization_engine import OptimizationEngine
from titan_x.services.strategy_builder import StrategyBuilder
from titan_x.services.walk_forward_engine import WalkForwardEngine


class StrategyValidationService:
    """Phase 5 orchestration over the existing backtest/optimization stack.

    This service does not create a second backtest engine. It separates train
    and test windows, optionally optimizes only on the train window, then runs
    the selected parameters on the later out-of-sample window.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._backtests = BacktestEngine(session)
        self._builder = StrategyBuilder(session)
        self._optimizer = OptimizationEngine(session)
        self._walk_forward = WalkForwardEngine()

    async def run_walk_forward(
        self,
        strategy_id: int,
        user_id: int,
        symbol: str,
        start_date: date,
        end_date: date,
        train_bars: int,
        test_bars: int,
        step_bars: int | None = None,
        initial_capital: float = 10000.0,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.001,
        parameter_ranges: dict[str, dict[str, Any]] | None = None,
        metric: str = "sharpe_ratio",
        direction: str = "maximize",
    ) -> dict[str, Any]:
        if start_date >= end_date:
            raise ValueError("start_date must be before end_date")
        if train_bars <= 0 or test_bars <= 0:
            raise ValueError("train_bars and test_bars must be positive")

        strategy = await self._session.get(
            __import__("titan_x.models.strategy", fromlist=["Strategy"]).Strategy,
            strategy_id,
        )
        if strategy is None or strategy.user_id != user_id:
            raise ValueError("Strategy not found")

        prices = await self._backtests._load_price_data(symbol, start_date, end_date)
        HistoricalDataValidator.validate(
            prices, symbol.upper(), start_date, end_date, minimum_bars=train_bars + test_bars,
        )
        windows = self._walk_forward.generate_windows(
            [p["date"] for p in prices], train_bars, test_bars, step_bars,
        )

        base_criteria = {
            "entry_criteria": json.loads(strategy.entry_criteria_json),
            "exit_criteria": json.loads(strategy.exit_criteria_json),
            "position_rules": json.loads(strategy.position_rules_json),
        }
        results: list[dict[str, Any]] = []

        for window in windows:
            train_start, train_end = window.train_start, window.train_end
            test_start, test_end = window.test_start, window.test_end
            selected_params: dict[str, Any] = {}

            if parameter_ranges:
                opt = await self._optimizer.run_optimization(
                    strategy_id=strategy_id,
                    user_id=user_id,
                    symbol=symbol,
                    start_date=train_start,
                    end_date=train_end,
                    parameter_ranges=parameter_ranges,
                    metric=metric,
                    direction=direction,
                    initial_capital=initial_capital,
                    commission_pct=commission_pct,
                    slippage_pct=slippage_pct,
                )
                if opt.get("best_params_json"):
                    selected_params = json.loads(opt["best_params_json"])

            criteria = base_criteria
            if selected_params:
                criteria = {
                    key: self._optimizer._substitute_params(value, selected_params)
                    for key, value in base_criteria.items()
                }

            train_result = await self._builder.run_backtest(
                strategy_id=strategy_id,
                user_id=user_id,
                symbol=symbol,
                start_date=train_start,
                end_date=train_end,
                initial_capital=initial_capital,
                commission_pct=commission_pct,
                slippage_pct=slippage_pct,
                criteria_override=criteria,
            )
            test_result = await self._builder.run_backtest(
                strategy_id=strategy_id,
                user_id=user_id,
                symbol=symbol,
                start_date=test_start,
                end_date=test_end,
                initial_capital=initial_capital,
                commission_pct=commission_pct,
                slippage_pct=slippage_pct,
                criteria_override=criteria,
            )

            train_metrics = train_result.get("metrics", {})
            test_metrics = test_result.get("metrics", {})
            results.append({
                "train_start": train_start.isoformat(),
                "train_end": train_end.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "selected_params": selected_params,
                "train_backtest_id": train_result["backtest_id"],
                "test_backtest_id": test_result["backtest_id"],
                "train_metrics": train_metrics,
                "test_metrics": test_metrics,
                "test_minus_train_return_pct": (
                    test_metrics.get("total_return_pct", 0.0)
                    - train_metrics.get("total_return_pct", 0.0)
                ),
            })

        return {
            "strategy_id": strategy_id,
            "symbol": symbol.upper(),
            "window_count": len(results),
            "train_bars": train_bars,
            "test_bars": test_bars,
            "step_bars": step_bars or test_bars,
            "metric": metric,
            "direction": direction,
            "windows": results,
        }
