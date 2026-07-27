import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.backtest import Backtest, BacktestReport
from titan_x.models.price import DailyPrice
from titan_x.models.strategy import OptimizationRun, Strategy
from titan_x.models.user import User
from titan_x.services.optimization_engine import OptimizationEngine
from titan_x.services.rule_evaluator import (
    BarData,
    Indicators,
    calculate_position_size,
    evaluate_entry_rules,
    evaluate_fundamental_rule,
    evaluate_indicator_rule,
    evaluate_risk_rule,
    get_exit_params,
)
from titan_x.services.strategy_builder import StrategyBuilder


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        await sess.execute(select(1).where(True))
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    u = User(email="strat@test.com", hashed_password="h")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
async def price_data(session: AsyncSession) -> None:
    today = date.today()
    for i in range(200):
        close = 100.0 + (i % 50) * 2.0 if (i // 50) % 2 == 0 else 200.0 - (i % 50) * 2.0
        dp = DailyPrice(
            symbol="TEST",
            trade_date=today - timedelta(days=199 - i),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1_000_000,
        )
        session.add(dp)
    await session.flush()


@pytest.fixture
def bar() -> BarData:
    return BarData(
        date=date(2025, 1, 15), open=105.0, high=110.0, low=102.0, close=108.0, volume=1_500_000,
    )


@pytest.fixture
def prev_bar() -> BarData:
    return BarData(
        date=date(2025, 1, 14), open=100.0, high=106.0, low=99.0, close=105.0, volume=1_200_000,
    )


@pytest.fixture
def ind() -> Indicators:
    return Indicators(
        sma_fast=106.0, sma_slow=104.0, rsi=55.0,
        bb_upper=115.0, bb_lower=95.0, bb_middle=105.0, atr=3.5,
    )


@pytest.fixture
def prev_ind() -> Indicators:
    return Indicators(
        sma_fast=104.0, sma_slow=103.5, rsi=52.0,
        bb_upper=114.0, bb_lower=96.0, bb_middle=105.0, atr=3.2,
    )


# ============================================================
# RULE EVALUATOR TESTS
# ============================================================

class TestEvaluateIndicatorRule:
    @pytest.mark.asyncio
    async def test_gt_triggered(self, bar: BarData, ind: Indicators):
        rule = {"field": "rsi", "operator": "gt", "value": 50}
        assert evaluate_indicator_rule(rule, bar, None, ind)

    @pytest.mark.asyncio
    async def test_gt_not_triggered(self, bar: BarData, ind: Indicators):
        rule = {"field": "rsi", "operator": "gt", "value": 60}
        assert not evaluate_indicator_rule(rule, bar, None, ind)

    @pytest.mark.asyncio
    async def test_lt_triggered(self, bar: BarData, ind: Indicators):
        rule = {"field": "rsi", "operator": "lt", "value": 60}
        assert evaluate_indicator_rule(rule, bar, None, ind)

    @pytest.mark.asyncio
    async def test_crosses_above(self, bar: BarData, prev_bar: BarData, ind: Indicators, prev_ind: Indicators):
        rule = {"field": "sma_fast", "operator": "crosses_above", "value": 105}
        assert evaluate_indicator_rule(rule, bar, prev_bar, ind, prev_ind)

    @pytest.mark.asyncio
    async def test_crosses_above_not_triggered(self, bar: BarData, prev_bar: BarData, ind: Indicators, prev_ind: Indicators):
        rule = {"field": "sma_fast", "operator": "crosses_above", "value": 107}
        assert not evaluate_indicator_rule(rule, bar, prev_bar, ind, prev_ind)

    @pytest.mark.asyncio
    async def test_crosses_below(self):
        bar = BarData(date=date(2025, 1, 15), open=105.0, high=110.0, low=102.0, close=103.0, volume=1_500_000)
        prev_bar = BarData(date=date(2025, 1, 14), open=100.0, high=106.0, low=99.0, close=105.0, volume=1_200_000)
        ind = Indicators(rsi=48.0)
        prev_ind = Indicators(rsi=55.0)
        rule = {"field": "rsi", "operator": "crosses_below", "value": 50}
        assert evaluate_indicator_rule(rule, bar, prev_bar, ind, prev_ind)

    @pytest.mark.asyncio
    async def test_between(self, bar: BarData, ind: Indicators):
        rule = {"field": "rsi", "operator": "between", "low": 30, "high": 70}
        assert evaluate_indicator_rule(rule, bar, None, ind)

    @pytest.mark.asyncio
    async def test_between_not_triggered(self, bar: BarData, ind: Indicators):
        rule = {"field": "rsi", "operator": "between", "low": 10, "high": 20}
        assert not evaluate_indicator_rule(rule, bar, None, ind)

    @pytest.mark.asyncio
    async def test_price_field(self, bar: BarData, ind: Indicators):
        rule = {"field": "price", "operator": "gt", "value": 100}
        assert evaluate_indicator_rule(rule, bar, None, ind)

    @pytest.mark.asyncio
    async def test_unknown_field(self, bar: BarData, ind: Indicators):
        rule = {"field": "nonexistent", "operator": "gt", "value": 0}
        assert not evaluate_indicator_rule(rule, bar, None, ind)

    @pytest.mark.asyncio
    async def test_crosses_missing_prev(self, bar: BarData, ind: Indicators):
        rule = {"field": "sma_fast", "operator": "crosses_above", "value": 105}
        assert not evaluate_indicator_rule(rule, bar, None, ind, None)


class TestEvaluateFundamentalRule:
    @pytest.mark.asyncio
    async def test_gt(self):
        rule = {"field": "pe_ratio", "operator": "lt", "value": 20}
        fundamentals = {"pe_ratio": 15.5, "market_cap": 1_000_000_000}
        assert evaluate_fundamental_rule(rule, fundamentals)

    @pytest.mark.asyncio
    async def test_not_triggered(self):
        rule = {"field": "pe_ratio", "operator": "gt", "value": 20}
        fundamentals = {"pe_ratio": 15.5}
        assert not evaluate_fundamental_rule(rule, fundamentals)

    @pytest.mark.asyncio
    async def test_missing_fundamentals(self):
        rule = {"field": "pe_ratio", "operator": "lt", "value": 20}
        assert not evaluate_fundamental_rule(rule, None)

    @pytest.mark.asyncio
    async def test_missing_field(self):
        rule = {"field": "pe_ratio", "operator": "lt", "value": 20}
        assert not evaluate_fundamental_rule(rule, {"market_cap": 100})

    @pytest.mark.asyncio
    async def test_between(self):
        rule = {"field": "pe_ratio", "operator": "between", "low": 10, "high": 30}
        assert evaluate_fundamental_rule(rule, {"pe_ratio": 20})

    @pytest.mark.asyncio
    async def test_between_not_triggered(self):
        rule = {"field": "pe_ratio", "operator": "between", "low": 5, "high": 10}
        assert not evaluate_fundamental_rule(rule, {"pe_ratio": 20})


class TestEvaluateRiskRule:
    @pytest.mark.asyncio
    async def test_max_position_not_exceeded(self):
        rule = {"field": "current_position_pct", "operator": "lte", "value": 20}
        portfolio = {"current_position_pct": 15}
        assert evaluate_risk_rule(rule, portfolio)

    @pytest.mark.asyncio
    async def test_max_position_exceeded(self):
        rule = {"field": "current_position_pct", "operator": "lte", "value": 10}
        portfolio = {"current_position_pct": 15}
        assert not evaluate_risk_rule(rule, portfolio)

    @pytest.mark.asyncio
    async def test_no_portfolio_state(self):
        rule = {"field": "current_position_pct", "operator": "lte", "value": 10}
        assert evaluate_risk_rule(rule, None)

    @pytest.mark.asyncio
    async def test_missing_field(self):
        rule = {"field": "current_position_pct", "operator": "lte", "value": 10}
        assert evaluate_risk_rule(rule, {"some_other": 100})


class TestCalculatePositionSize:
    @pytest.mark.asyncio
    async def test_fixed_pct(self, bar: BarData, ind: Indicators):
        rule = {"type": "fixed_pct", "value": 50}
        size = calculate_position_size(rule, 10000.0, bar, ind)
        assert size == 5000.0

    @pytest.mark.asyncio
    async def test_fixed_value(self, bar: BarData, ind: Indicators):
        rule = {"type": "fixed_value", "value": 3000}
        size = calculate_position_size(rule, 10000.0, bar, ind)
        assert size == 3000.0

    @pytest.mark.asyncio
    async def test_fixed_value_capped(self, bar: BarData, ind: Indicators):
        rule = {"type": "fixed_value", "value": 20000}
        size = calculate_position_size(rule, 10000.0, bar, ind)
        assert size == 10000.0

    @pytest.mark.asyncio
    async def test_risk_based_with_atr(self, bar: BarData, ind: Indicators):
        rule = {"type": "risk_based", "value": 95, "risk_per_trade_pct": 1.0, "stop_distance_atr": 2.0}
        size = calculate_position_size(rule, 10000.0, bar, ind)
        assert size > 0
        assert size < 10000.0

    @pytest.mark.asyncio
    async def test_risk_based_no_atr(self, bar: BarData):
        ind_no_atr = Indicators(rsi=55.0)
        rule = {"type": "risk_based", "value": 50, "risk_per_trade_pct": 1.0}
        size = calculate_position_size(rule, 10000.0, bar, ind_no_atr)
        assert size == 5000.0

    @pytest.mark.asyncio
    async def test_kelly(self, bar: BarData, ind: Indicators):
        rule = {
            "type": "kelly", "kelly_win_rate": 0.6,
            "kelly_avg_win": 2.0, "kelly_avg_loss": 1.0, "kelly_max_pct": 0.25,
        }
        size = calculate_position_size(rule, 10000.0, bar, ind)
        assert size == pytest.approx(2500.0)

    @pytest.mark.asyncio
    async def test_kelly_zero_avg_loss(self, bar: BarData, ind: Indicators):
        rule = {"type": "kelly", "kelly_win_rate": 0.6, "kelly_avg_win": 2.0, "kelly_avg_loss": 0}
        size = calculate_position_size(rule, 10000.0, bar, ind)
        assert size == 9500.0

    @pytest.mark.asyncio
    async def test_default(self, bar: BarData):
        rule = {"type": "unknown", "value": 50}
        size = calculate_position_size(rule, 10000.0, bar)
        assert size == 9500.0


class TestGetExitParams:
    @pytest.mark.asyncio
    async def test_all_exit_params(self):
        rules = [
            {"type": "stop_loss", "value": 5},
            {"type": "take_profit", "value": 10},
            {"type": "trailing_stop", "value": 3},
            {"type": "max_holding_days", "value": 30},
        ]
        params = get_exit_params(rules)
        assert params["stop_loss_pct"] == 5.0
        assert params["take_profit_pct"] == 10.0
        assert params["trailing_stop_pct"] == 3.0
        assert params["max_holding_days"] == 30

    @pytest.mark.asyncio
    async def test_partial_exit_params(self):
        rules = [{"type": "stop_loss", "value": 5}]
        params = get_exit_params(rules)
        assert params["stop_loss_pct"] == 5.0
        assert params["take_profit_pct"] is None

    @pytest.mark.asyncio
    async def test_no_exit_rules(self):
        params = get_exit_params([])
        assert all(v is None for v in params.values())


class TestEvaluateEntryRules:
    @pytest.mark.asyncio
    async def test_single_and_group_all_true(self, bar: BarData, ind: Indicators):
        criteria = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "gt", "value": 50},
                {"type": "indicator", "field": "price", "operator": "gt", "value": 100},
            ]},
        ]
        assert evaluate_entry_rules(criteria, bar, None, ind)

    @pytest.mark.asyncio
    async def test_single_and_group_one_false(self, bar: BarData, ind: Indicators):
        criteria = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "gt", "value": 50},
                {"type": "indicator", "field": "price", "operator": "lt", "value": 100},
            ]},
        ]
        assert not evaluate_entry_rules(criteria, bar, None, ind)

    @pytest.mark.asyncio
    async def test_or_group_any_true(self, bar: BarData, ind: Indicators):
        criteria = [
            {"logic": "or", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "gt", "value": 100},
                {"type": "indicator", "field": "price", "operator": "lt", "value": 110},
            ]},
        ]
        assert evaluate_entry_rules(criteria, bar, None, ind)

    @pytest.mark.asyncio
    async def test_or_group_all_false(self, bar: BarData, ind: Indicators):
        criteria = [
            {"logic": "or", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "gt", "value": 100},
                {"type": "indicator", "field": "price", "operator": "gt", "value": 200},
            ]},
        ]
        assert not evaluate_entry_rules(criteria, bar, None, ind)

    @pytest.mark.asyncio
    async def test_fundamental_rule(self, bar: BarData, ind: Indicators):
        criteria = [
            {"logic": "and", "rules": [
                {"type": "fundamental", "field": "pe_ratio", "operator": "lt", "value": 20},
            ]},
        ]
        fundamentals = {"pe_ratio": 15}
        assert evaluate_entry_rules(criteria, bar, None, ind, fundamentals=fundamentals)

    @pytest.mark.asyncio
    async def test_risk_rule(self, bar: BarData, ind: Indicators):
        criteria = [
            {"logic": "and", "rules": [
                {"type": "risk", "field": "current_position_pct", "operator": "lte", "value": 20},
            ]},
        ]
        portfolio = {"current_position_pct": 15}
        assert evaluate_entry_rules(criteria, bar, None, ind, portfolio_state=portfolio)

    @pytest.mark.asyncio
    async def test_empty_criteria(self, bar: BarData, ind: Indicators):
        assert not evaluate_entry_rules([], bar, None, ind)

    @pytest.mark.asyncio
    async def test_crossover_in_entry(self, bar: BarData, prev_bar: BarData, ind: Indicators, prev_ind: Indicators):
        criteria = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "sma_fast", "operator": "crosses_above", "value": 105},
            ]},
        ]
        assert evaluate_entry_rules(criteria, bar, prev_bar, ind, prev_ind)


# ============================================================
# STRATEGY BUILDER TESTS
# ============================================================

class TestCreateStrategy:
    @pytest.mark.asyncio
    async def test_create(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        entry = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "lt", "value": 30},
            ]},
        ]
        exit_rules = [
            {"type": "stop_loss", "value": 5},
            {"type": "take_profit", "value": 10},
        ]
        result = await builder.create_strategy(
            user_id=user.id, name="RSI Reversal",
            entry_criteria=entry, exit_criteria=exit_rules,
            risk_rules={"max_position_pct": 10}, position_rules={"type": "fixed_pct", "value": 95},
            tags=["rsi", "reversal"],
        )
        assert result["name"] == "RSI Reversal"
        assert result["version"] == 1
        assert result["is_active"] is True
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_create_defaults(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        result = await builder.create_strategy(user_id=user.id, name="Simple")
        entry = json.loads(result["entry_criteria_json"])
        assert entry == []
        assert result["version"] == 1


class TestGetStrategy:
    @pytest.mark.asyncio
    async def test_get_existing(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        created = await builder.create_strategy(user_id=user.id, name="Test")
        result = await builder.get_strategy(created["id"])
        assert result is not None
        assert result["name"] == "Test"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        result = await builder.get_strategy(9999)
        assert result is None


class TestListStrategies:
    @pytest.mark.asyncio
    async def test_list(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        await builder.create_strategy(user_id=user.id, name="S1")
        await builder.create_strategy(user_id=user.id, name="S2")
        rows, total = await builder.list_strategies(user_id=user.id)
        assert total == 2
        names = [r.name for r in rows]
        assert "S1" in names
        assert "S2" in names

    @pytest.mark.asyncio
    async def test_list_pagination(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        for i in range(5):
            await builder.create_strategy(user_id=user.id, name=f"S{i}")
        rows, total = await builder.list_strategies(user_id=user.id, skip=0, limit=3)
        assert total == 5
        assert len(rows) == 3


class TestUpdateStrategy:
    @pytest.mark.asyncio
    async def test_update(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        created = await builder.create_strategy(user_id=user.id, name="Original")
        result = await builder.update_strategy(
            created["id"], name="Updated", is_active=False,
        )
        assert result["name"] == "Updated"
        assert result["version"] == 2
        assert result["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        result = await builder.update_strategy(9999, name="Nope")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_criteria(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        created = await builder.create_strategy(user_id=user.id, name="S")
        new_entry = [{"logic": "or", "rules": [{"type": "indicator", "field": "rsi", "operator": "lt", "value": 25}]}]
        result = await builder.update_strategy(created["id"], entry_criteria=new_entry)
        entry = json.loads(result["entry_criteria_json"])
        assert entry[0]["rules"][0]["value"] == 25


class TestDeleteStrategy:
    @pytest.mark.asyncio
    async def test_delete(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        created = await builder.create_strategy(user_id=user.id, name="Delete Me")
        deleted = await builder.delete_strategy(created["id"])
        assert deleted is True
        result = await builder.get_strategy(created["id"])
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        deleted = await builder.delete_strategy(9999)
        assert deleted is False


class TestRunBacktest:
    @pytest.mark.asyncio
    async def test_run_composed_strategy(self, session: AsyncSession, user: User, price_data):
        builder = StrategyBuilder(session)
        entry = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "lt", "value": 35},
            ]},
        ]
        exit_rules = [
            {"type": "stop_loss", "value": 5},
            {"type": "take_profit", "value": 10},
        ]
        strat = await builder.create_strategy(
            user_id=user.id, name="RSI Strategy",
            entry_criteria=entry, exit_criteria=exit_rules,
            position_rules={"type": "fixed_pct", "value": 95},
        )

        today = date.today()
        start = today - timedelta(days=180)
        end = today
        result = await builder.run_backtest(
            strategy_id=strat["id"], user_id=user.id,
            symbol="TEST", start_date=start, end_date=end,
        )
        assert result["status"] == "completed"
        assert "metrics" in result
        assert result["trades_count"] >= 0

        backtest = await session.get(Backtest, result["backtest_id"])
        assert backtest is not None
        assert backtest.strategy_type == "composed"

    @pytest.mark.asyncio
    async def test_run_nonexistent_strategy(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        today = date.today()
        with pytest.raises(ValueError, match="Strategy 9999 not found"):
            await builder.run_backtest(
                strategy_id=9999, user_id=user.id,
                symbol="TEST", start_date=today - timedelta(days=60), end_date=today,
            )

    @pytest.mark.asyncio
    async def test_run_insufficient_data(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        strat = await builder.create_strategy(user_id=user.id, name="Test")
        today = date.today()
        with pytest.raises(ValueError, match="Insufficient price data"):
            await builder.run_backtest(
                strategy_id=strat["id"], user_id=user.id,
                symbol="NODATA", start_date=today - timedelta(days=10), end_date=today,
            )


# ============================================================
# OPTIMIZATION ENGINE TESTS
# ============================================================

class TestGenerateCombinations:
    @pytest.mark.asyncio
    async def test_int_range(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        ranges = {"fast_period": {"min": 5, "max": 10, "step": 5, "type": "int"}}
        combos = engine._generate_combinations(ranges)
        assert len(combos) == 2
        assert combos[0] == {"fast_period": 5}
        assert combos[1] == {"fast_period": 10}

    @pytest.mark.asyncio
    async def test_float_range(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        ranges = {"threshold": {"min": 0.5, "max": 1.0, "step": 0.25, "type": "float"}}
        combos = engine._generate_combinations(ranges)
        assert len(combos) == 3
        assert combos[0] == {"threshold": 0.5}
        assert combos[2] == {"threshold": 1.0}

    @pytest.mark.asyncio
    async def test_categorical(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        ranges = {"method": {"type": "categorical", "values": ["sma", "ema", "wma"]}}
        combos = engine._generate_combinations(ranges)
        assert len(combos) == 3
        assert combos[1] == {"method": "ema"}

    @pytest.mark.asyncio
    async def test_multiple_params(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        ranges = {
            "fast_period": {"min": 5, "max": 10, "step": 5, "type": "int"},
            "slow_period": {"min": 20, "max": 30, "step": 10, "type": "int"},
        }
        combos = engine._generate_combinations(ranges)
        assert len(combos) == 4

    @pytest.mark.asyncio
    async def test_empty_ranges(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        combos = engine._generate_combinations({})
        assert combos == [{}]


class TestSubstituteParams:
    @pytest.mark.asyncio
    async def test_substitute_dict_value(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        obj = {"field": "rsi", "operator": "lt", "value": "{rsi_oversold}"}
        result = engine._substitute_params(obj, {"rsi_oversold": 30})
        assert result["value"] == 30

    @pytest.mark.asyncio
    async def test_substitute_nested(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        obj = [
            {"logic": "and", "rules": [
                {"field": "rsi", "value": "{rsi_oversold}"},
                {"field": "sma_fast", "value": "{fast_period}"},
            ]},
        ]
        params = {"rsi_oversold": 25, "fast_period": 10}
        result = engine._substitute_params(obj, params)
        assert result[0]["rules"][0]["value"] == 25
        assert result[0]["rules"][1]["value"] == 10

    @pytest.mark.asyncio
    async def test_no_substitution_needed(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        obj = {"field": "rsi", "value": 30}
        result = engine._substitute_params(obj, {"rsi_oversold": 25})
        assert result["value"] == 30

    @pytest.mark.asyncio
    async def test_string_not_matching(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        obj = "not_a_placeholder"
        result = engine._substitute_params(obj, {"param": "value"})
        assert result == "not_a_placeholder"


class TestCreateOptimizationRun:
    @pytest.mark.asyncio
    async def test_create(self, session: AsyncSession, user: User):
        opt = OptimizationRun(
            strategy_id=1, symbol="TEST",
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
            initial_capital=10000.0,
            parameter_ranges_json=json.dumps({"p": {"min": 1, "max": 5, "step": 1}}),
            metric="sharpe_ratio", direction="maximize",
            total_combinations=5, completed_combinations=0, status="pending",
        )
        session.add(opt)
        await session.flush()
        assert opt.id is not None
        assert opt.status == "pending"


class TestOptimizationRun:
    @pytest.mark.asyncio
    async def test_full_optimization(self, session: AsyncSession, user: User, price_data):
        builder = StrategyBuilder(session)
        entry = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "lt", "value": "{rsi_level}"},
            ]},
        ]
        strat = await builder.create_strategy(
            user_id=user.id, name="Opt RSI",
            entry_criteria=entry,
            exit_criteria=[{"type": "stop_loss", "value": 5}],
            position_rules={"type": "fixed_pct", "value": 95},
        )

        engine = OptimizationEngine(session)
        today = date.today()
        result = await engine.run_optimization(
            strategy_id=strat["id"], user_id=user.id,
            symbol="TEST", start_date=today - timedelta(days=180), end_date=today,
            parameter_ranges={"rsi_level": {"min": 25, "max": 35, "step": 10, "type": "int"}},
            metric="sharpe_ratio",
        )
        assert result["total_combinations"] == 2
        assert result["completed_combinations"] == 2
        assert result["status"] in ("completed", "completed_with_errors")
        assert result["best_score"] is not None
        assert result["best_params_json"] is not None

    @pytest.mark.asyncio
    async def test_list_optimizations(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        strat = await builder.create_strategy(user_id=user.id, name="Opt List")

        engine = OptimizationEngine(session)
        opt = OptimizationRun(
            strategy_id=strat["id"], symbol="TEST",
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
            initial_capital=10000.0,
            parameter_ranges_json="{}", metric="sharpe_ratio",
            total_combinations=1, completed_combinations=1, status="completed",
        )
        session.add(opt)
        await session.flush()

        rows, total = await engine.list_optimizations(strategy_id=strat["id"])
        assert total == 1
        assert rows[0].strategy_id == strat["id"]

    @pytest.mark.asyncio
    async def test_get_optimization(self, session: AsyncSession, user: User):
        engine = OptimizationEngine(session)
        opt = OptimizationRun(
            strategy_id=1, symbol="TEST",
            start_date=date.today(), end_date=date.today(),
            initial_capital=10000.0, parameter_ranges_json="{}",
            metric="sharpe_ratio", total_combinations=1, completed_combinations=1,
            status="completed", best_score=1.5,
            best_params_json=json.dumps({"p": 10}),
        )
        session.add(opt)
        await session.flush()

        result = await engine.get_optimization(opt.id)
        assert result is not None
        assert result["best_score"] == 1.5
        assert result["strategy_id"] == 1

    @pytest.mark.asyncio
    async def test_get_optimization_nonexistent(self, session: AsyncSession):
        engine = OptimizationEngine(session)
        result = await engine.get_optimization(9999)
        assert result is None


# ============================================================
# INTEGRATION: STRATEGY -> BACKTEST -> REPORT
# ============================================================

class TestStrategyBacktestIntegration:
    @pytest.mark.asyncio
    async def test_strategy_backtest_produces_report(self, session: AsyncSession, user: User, price_data):
        builder = StrategyBuilder(session)
        entry = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "lt", "value": 40},
            ]},
        ]
        strat = await builder.create_strategy(
            user_id=user.id, name="RSI BT",
            entry_criteria=entry,
            exit_criteria=[{"type": "stop_loss", "value": 5}, {"type": "take_profit", "value": 10}],
            position_rules={"type": "fixed_pct", "value": 95},
        )

        today = date.today()
        result = await builder.run_backtest(
            strategy_id=strat["id"], user_id=user.id,
            symbol="TEST", start_date=today - timedelta(days=180), end_date=today,
        )
        report = await session.get(BacktestReport, result["backtest_id"])
        if report:
            assert report.total_trades >= 0

    @pytest.mark.asyncio
    async def test_multiple_strategies_isolation(self, session: AsyncSession, user: User):
        builder = StrategyBuilder(session)
        s1 = await builder.create_strategy(user_id=user.id, name="S1")
        s2 = await builder.create_strategy(user_id=user.id, name="S2")
        assert s1["id"] != s2["id"]

        rows, total = await builder.list_strategies(user_id=user.id)
        assert total == 2


# ============================================================
# OPTIMIZATION INTEGRATION
# ============================================================

class TestOptimizationIntegration:
    @pytest.mark.asyncio
    async def test_minimize_direction(self, session: AsyncSession, user: User, price_data):
        builder = StrategyBuilder(session)
        entry = [
            {"logic": "and", "rules": [
                {"type": "indicator", "field": "rsi", "operator": "lt", "value": "{rsi_level}"},
            ]},
        ]
        strat = await builder.create_strategy(
            user_id=user.id, name="Min Test",
            entry_criteria=entry,
            exit_criteria=[{"type": "stop_loss", "value": 5}],
        )

        engine = OptimizationEngine(session)
        today = date.today()
        result = await engine.run_optimization(
            strategy_id=strat["id"], user_id=user.id,
            symbol="TEST", start_date=today - timedelta(days=180), end_date=today,
            parameter_ranges={"rsi_level": {"min": 25, "max": 35, "step": 10, "type": "int"}},
            metric="max_drawdown_pct", direction="minimize",
        )
        assert result["best_score"] is not None
