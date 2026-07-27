import itertools
import json
from datetime import date, datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.backtest import Backtest
from titan_x.models.strategy import OptimizationRun, Strategy
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.strategy_builder import StrategyBuilder

logger = structlog.get_logger(__name__)


class OptimizationEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._opt_repo = BaseRepository(session, OptimizationRun)

    async def run_optimization(
        self,
        strategy_id: int,
        user_id: int,
        symbol: str,
        start_date: date,
        end_date: date,
        parameter_ranges: dict[str, dict[str, Any]],
        metric: str = "sharpe_ratio",
        direction: str = "maximize",
        initial_capital: float = 10000.0,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.001,
    ) -> dict[str, Any]:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        combinations = self._generate_combinations(parameter_ranges)
        total = len(combinations)

        opt_run = await self._opt_repo.create(
            strategy_id=strategy_id,
            symbol=symbol.upper(),
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            parameter_ranges_json=json.dumps(parameter_ranges),
            metric=metric,
            direction=direction,
            total_combinations=total,
            completed_combinations=0,
            status="running",
            started_at=datetime.now(tz=timezone.utc),
        )

        best_score: float | None = None
        best_params: dict[str, Any] | None = None
        best_result: dict[str, Any] | None = None

        engine = BacktestEngine(self._session)
        builder = StrategyBuilder(self._session)

        completed = 0
        errors = 0

        for combo in combinations:
            try:
                entry_criteria = self._substitute_params(
                    json.loads(strategy.entry_criteria_json), combo,
                )
                exit_criteria = self._substitute_params(
                    json.loads(strategy.exit_criteria_json), combo,
                )
                risk_rules = self._substitute_params(
                    json.loads(strategy.risk_rules_json), combo,
                )
                position_rules = self._substitute_params(
                    json.loads(strategy.position_rules_json), combo,
                )

                await builder.update_strategy(
                    strategy_id=strategy_id,
                    entry_criteria=entry_criteria,
                    exit_criteria=exit_criteria,
                    risk_rules=risk_rules,
                    position_rules=position_rules,
                )

                result = await builder.run_backtest(
                    strategy_id=strategy_id,
                    user_id=user_id,
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                    commission_pct=commission_pct,
                    slippage_pct=slippage_pct,
                )

                metrics = result.get("metrics", {})
                score = metrics.get(metric, 0.0)

                if best_score is None:
                    best_score = score
                    best_params = combo
                    best_result = metrics
                elif direction == "maximize" and score > best_score:
                    best_score = score
                    best_params = combo
                    best_result = metrics
                elif direction == "minimize" and score < best_score:
                    best_score = score
                    best_params = combo
                    best_result = metrics

                completed += 1

            except Exception as exc:
                errors += 1
                logger.warning("optimization_combo_failed", combo=combo, error=str(exc))
                completed += 1

            opt_run.completed_combinations = completed
            await self._session.flush()

        opt_run.status = "completed" if errors == 0 else "completed_with_errors"
        opt_run.completed_at = datetime.now(tz=timezone.utc)
        opt_run.best_params_json = json.dumps(best_params) if best_params else None
        opt_run.best_score = best_score
        opt_run.best_result_json = json.dumps(best_result) if best_result else None
        await self._session.flush()

        return self._opt_to_dict(opt_run)

    def _generate_combinations(self, ranges: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        param_values: dict[str, list[Any]] = {}
        for param_name, rng in ranges.items():
            values: list[Any] = []
            param_type = rng.get("type", "int")

            if param_type == "categorical":
                values = rng.get("values", [])
            else:
                start_val = rng["min"]
                end_val = rng["max"]
                step = rng.get("step", 1)

                if param_type == "int":
                    values = list(range(int(start_val), int(end_val) + 1, int(step)))
                elif param_type == "float":
                    current = float(start_val)
                    while current <= float(end_val):
                        values.append(round(current, 4))
                        current += float(step)

            param_values[param_name] = values

        if not param_values:
            return [{}]

        keys = list(param_values.keys())
        combos = list(itertools.product(*(param_values[k] for k in keys)))
        return [dict(zip(keys, combo, strict=False)) for combo in combos]

    def _substitute_params(
        self,
        obj: Any,
        params: dict[str, Any],
    ) -> Any:
        if isinstance(obj, dict):
            return {k: self._substitute_params(v, params) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_params(item, params) for item in obj]
        elif isinstance(obj, str):
            for param_name, param_value in params.items():
                placeholder = f"{{{param_name}}}"
                if placeholder in obj:
                    return param_value
            return obj
        return obj

    async def get_optimization(self, opt_id: int) -> dict[str, Any] | None:
        opt = await self._opt_repo.get(opt_id)
        if opt is None:
            return None
        return self._opt_to_dict(opt)

    async def list_optimizations(
        self, strategy_id: int | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[list[OptimizationRun], int]:
        from sqlalchemy import desc, func, select
        count_query = select(func.count()).select_from(OptimizationRun)
        query = select(OptimizationRun).order_by(desc(OptimizationRun.created_at))
        if strategy_id is not None:
            query = query.where(OptimizationRun.strategy_id == strategy_id)
            count_query = count_query.where(OptimizationRun.strategy_id == strategy_id)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return list(rows), total

    def _opt_to_dict(self, opt: OptimizationRun) -> dict[str, Any]:
        return {
            "id": opt.id,
            "strategy_id": opt.strategy_id,
            "symbol": opt.symbol,
            "start_date": opt.start_date.isoformat() if opt.start_date else None,
            "end_date": opt.end_date.isoformat() if opt.end_date else None,
            "initial_capital": opt.initial_capital,
            "parameter_ranges_json": opt.parameter_ranges_json,
            "metric": opt.metric,
            "direction": opt.direction,
            "total_combinations": opt.total_combinations,
            "completed_combinations": opt.completed_combinations,
            "best_params_json": opt.best_params_json,
            "best_score": opt.best_score,
            "best_result_json": opt.best_result_json,
            "status": opt.status,
            "started_at": opt.started_at.isoformat() if opt.started_at else None,
            "completed_at": opt.completed_at.isoformat() if opt.completed_at else None,
            "error_message": opt.error_message,
            "created_at": opt.created_at.isoformat() if opt.created_at else None,
        }
