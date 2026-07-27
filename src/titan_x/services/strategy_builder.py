import json
import math
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.backtest import Backtest
from titan_x.models.strategy import OptimizationRun, Strategy
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.rule_evaluator import (
    BarData,
    Indicators,
    calculate_position_size,
    evaluate_entry_rules,
    get_exit_params,
)

logger = structlog.get_logger(__name__)


class StrategyBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, Strategy)

    async def create_strategy(
        self,
        user_id: int,
        name: str,
        entry_criteria: list[dict[str, Any]] | None = None,
        exit_criteria: list[dict[str, Any]] | None = None,
        risk_rules: dict[str, Any] | None = None,
        position_rules: dict[str, Any] | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        strategy = await self._repo.create(
            user_id=user_id,
            name=name,
            description=description,
            entry_criteria_json=json.dumps(entry_criteria or []),
            exit_criteria_json=json.dumps(exit_criteria or []),
            risk_rules_json=json.dumps(risk_rules or {}),
            position_rules_json=json.dumps(position_rules or {}),
            tags_json=json.dumps(tags or []),
            version=1,
            is_active=True,
        )
        return self._to_dict(strategy)

    async def get_strategy(self, strategy_id: int) -> dict[str, Any] | None:
        strategy = await self._repo.get(strategy_id)
        if strategy is None:
            return None
        return self._to_dict(strategy)

    async def list_strategies(
        self, user_id: int | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[Strategy], int]:
        count_query = select(func.count()).select_from(Strategy)
        query = select(Strategy).order_by(desc(Strategy.updated_at))
        if user_id is not None:
            query = query.where(Strategy.user_id == user_id)
            count_query = count_query.where(Strategy.user_id == user_id)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_strategy(
        self,
        strategy_id: int,
        name: str | None = None,
        description: str | None = None,
        entry_criteria: list[dict[str, Any]] | None = None,
        exit_criteria: list[dict[str, Any]] | None = None,
        risk_rules: dict[str, Any] | None = None,
        position_rules: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any] | None:
        strategy = await self._repo.get(strategy_id)
        if strategy is None:
            return None

        if name is not None:
            strategy.name = name
        if description is not None:
            strategy.description = description
        if entry_criteria is not None:
            strategy.entry_criteria_json = json.dumps(entry_criteria)
        if exit_criteria is not None:
            strategy.exit_criteria_json = json.dumps(exit_criteria)
        if risk_rules is not None:
            strategy.risk_rules_json = json.dumps(risk_rules)
        if position_rules is not None:
            strategy.position_rules_json = json.dumps(position_rules)
        if tags is not None:
            strategy.tags_json = json.dumps(tags)
        if is_active is not None:
            strategy.is_active = is_active
        strategy.version += 1
        await self._session.flush()
        await self._session.refresh(strategy)
        return self._to_dict(strategy)

    async def delete_strategy(self, strategy_id: int) -> bool:
        return await self._repo.delete(strategy_id)

    async def run_backtest(
        self,
        strategy_id: int,
        user_id: int,
        symbol: str,
        start_date: date,
        end_date: date,
        initial_capital: float = 10000.0,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.001,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        strategy = await self._repo.get(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        entry_criteria = json.loads(strategy.entry_criteria_json)
        exit_criteria = json.loads(strategy.exit_criteria_json)
        position_rules = json.loads(strategy.position_rules_json)
        exit_params = get_exit_params(exit_criteria)

        engine = BacktestEngine(self._session)
        strategy_params: dict[str, Any] = {
            "entry_criteria": entry_criteria,
            "exit_criteria": exit_criteria,
            "position_rules": position_rules,
            "exit_params": exit_params,
            "strategy_id": strategy_id,
        }

        backtest = await engine.create_backtest(
            user_id=user_id,
            name=f"[Strategy] {strategy.name}",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            strategy_type="composed",
            strategy_params=strategy_params,
            config=config or {},
            description=strategy.description,
        )

        backtest_id = backtest["id"]
        backtest_obj = await self._session.get(Backtest, backtest_id)

        prices = await engine._load_price_data(symbol, start_date, end_date)
        if len(prices) < 30:
            raise ValueError(f"Insufficient price data for {symbol}: {len(prices)} bars")

        indicators_raw = engine._compute_indicators(prices, "sma_crossover", {})

        signals = self._generate_strategy_signals(
            prices, indicators_raw, entry_criteria, exit_criteria, position_rules, exit_params,
        )

        backtest_obj.strategy_type = "composed"
        await self._session.flush()

        result = await engine._execute_backtest(backtest_obj)
        return result

    def _prepare_price_indicators(
        self,
        prices: list[dict[str, Any]],
        indicators_raw: dict[str, list[float | None]],
        idx: int,
    ) -> tuple[BarData, Indicators]:
        p = prices[idx]
        bar = BarData(
            date=p["date"], open=p["open"], high=p["high"],
            low=p["low"], close=p["close"], volume=p["volume"],
        )
        ind = Indicators(
            sma_fast=indicators_raw["sma_fast"][idx],
            sma_slow=indicators_raw["sma_slow"][idx],
            rsi=indicators_raw["rsi"][idx],
            bb_upper=indicators_raw["bb_upper"][idx],
            bb_lower=indicators_raw["bb_lower"][idx],
            bb_middle=indicators_raw["bb_middle"][idx],
            atr=indicators_raw["atr"][idx],
        )
        return bar, ind

    def _generate_strategy_signals(
        self,
        prices: list[dict[str, Any]],
        indicators_raw: dict[str, list[float | None]],
        entry_criteria: list[dict[str, Any]],
        exit_criteria: list[dict[str, Any]],
        position_rules: dict[str, Any],
        exit_params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        has_position = False
        position_bar: BarData | None = None
        prev_bar: BarData | None = None
        prev_ind: Indicators | None = None

        for i in range(len(prices)):
            bar, ind = self._prepare_price_indicators(prices, indicators_raw, i)

            if not has_position and evaluate_entry_rules(entry_criteria, bar, prev_bar, ind, prev_ind):
                signals.append({
                    "signal_date": bar.date,
                    "action": "buy",
                    "price": bar.close,
                    "confidence": 1.0,
                    "signal_type": "composed_entry",
                    "source": "strategy_builder",
                    "stop_loss_pct": exit_params.get("stop_loss_pct"),
                    "take_profit_pct": exit_params.get("take_profit_pct"),
                    "metadata_json": json.dumps({"strategy_trigger": "entry_rules"}),
                })
                has_position = True
                position_bar = bar

            prev_bar = bar
            prev_ind = ind

        return signals

    def _to_dict(self, strategy: Strategy) -> dict[str, Any]:
        return {
            "id": strategy.id,
            "user_id": strategy.user_id,
            "name": strategy.name,
            "description": strategy.description,
            "entry_criteria_json": strategy.entry_criteria_json,
            "exit_criteria_json": strategy.exit_criteria_json,
            "risk_rules_json": strategy.risk_rules_json,
            "position_rules_json": strategy.position_rules_json,
            "tags_json": strategy.tags_json,
            "version": strategy.version,
            "is_active": strategy.is_active,
            "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
            "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
        }
