from datetime import date, timedelta

import pytest

from titan_x.services.portfolio_backtest_engine import PortfolioBacktestEngine


def _series(start: float, step: float = 1.0):
    d = date(2026, 1, 1)
    return [(d + timedelta(days=i), start + step * i) for i in range(5)]


def test_multi_asset_backtest_and_allocation() -> None:
    engine = PortfolioBacktestEngine()
    result = engine.run(
        {"AAA": _series(100), "BBB": _series(200, 2)},
        {"AAA": 60, "BBB": 40},
        100_000,
    )
    assert result["symbols"] == ["AAA", "BBB"]
    assert result["allocations"] == {"AAA": 60.0, "BBB": 40.0}
    assert len(result["equity_curve"]) == 5
    assert result["ending_equity"] > result["initial_capital"]


def test_weights_are_normalized() -> None:
    result = PortfolioBacktestEngine().run(
        {"AAA": _series(100), "BBB": _series(100)},
        {"AAA": 3, "BBB": 1},
        1000,
    )
    assert result["allocations"] == {"AAA": 75.0, "BBB": 25.0}


def test_cost_parameters_reduce_invested_capital() -> None:
    base = PortfolioBacktestEngine().run({"AAA": _series(100)}, {"AAA": 1}, 10000)
    cost = PortfolioBacktestEngine().run(
        {"AAA": _series(100)}, {"AAA": 1}, 10000, commission_bps=10, slippage_bps=10
    )
    assert cost["ending_equity"] < base["ending_equity"]


def test_rejects_missing_common_dates() -> None:
    prices = {"AAA": _series(100), "BBB": _series(100)[:-4]}
    with pytest.raises(ValueError, match="two common trading dates"):
        PortfolioBacktestEngine().run(prices, {"AAA": 1, "BBB": 1}, 1000)


def test_drawdown_is_non_positive() -> None:
    result = PortfolioBacktestEngine().run(
        {"AAA": [(date(2026, 1, 1), 100), (date(2026, 1, 2), 80), (date(2026, 1, 3), 90)]},
        {"AAA": 1},
        1000,
    )
    assert result["max_drawdown_pct"] < 0
