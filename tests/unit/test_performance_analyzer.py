from datetime import date

import pytest

from titan_x.services.performance_analyzer import PerformanceAnalyzer


def test_average_drawdown_uses_currency_and_percentage_separately():
    analyzer = PerformanceAnalyzer()
    result = analyzer.calculate_drawdown(
        [
            {"date": date(2026, 1, 1), "equity": 1000.0},
            {"date": date(2026, 1, 2), "equity": 900.0},
            {"date": date(2026, 1, 3), "equity": 950.0},
        ]
    )

    assert result["max_drawdown"] == 100.0
    assert result["max_drawdown_pct"] == 10.0
    assert result["avg_drawdown"] == 75.0
    assert result["avg_drawdown_pct"] == 7.5


def test_performance_analyzer_handles_no_drawdown():
    analyzer = PerformanceAnalyzer()
    result = analyzer.calculate_drawdown(
        [
            {"date": date(2026, 1, 1), "equity": 1000.0},
            {"date": date(2026, 1, 2), "equity": 1050.0},
        ]
    )

    assert result["max_drawdown"] == 0.0
    assert result["max_drawdown_pct"] == 0.0
    assert result["avg_drawdown"] == 0.0
    assert result["avg_drawdown_pct"] == 0.0


def test_daily_returns_and_sharpe_are_based_on_equity_curve():
    analyzer = PerformanceAnalyzer()
    curve = [
        {"equity": 1000.0},
        {"equity": 1100.0},
        {"equity": 1050.0},
    ]

    returns = analyzer.calculate_daily_returns(curve)

    assert returns == [0.1, -50 / 1100]
    assert analyzer.calculate_sharpe(returns) is not None


def test_equity_curve_uses_execution_prices_and_costs():
    analyzer = PerformanceAnalyzer()
    curve = analyzer.generate_equity_curve(
        [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        [100.0, 110.0, 120.0],
        [
            {
                "symbol": "TEST",
                "entry_date": date(2026, 1, 1),
                "exit_date": date(2026, 1, 3),
                "quantity": 5,
                "entry_price": 100.0,
                "exit_price": 120.0,
                "entry_commission": 2.0,
                "exit_commission": 3.0,
            }
        ],
        1000.0,
    )

    assert curve[0]["cash"] == 498.0
    assert curve[0]["holdings_value"] == 500.0
    assert curve[0]["equity"] == 998.0
    assert curve[1]["equity"] == 1048.0
    assert curve[2]["cash"] == 1095.0
    assert curve[2]["holdings_value"] == 0.0
    assert curve[2]["equity"] == 1095.0
    assert curve[2]["returns_pct"] == pytest.approx((1095.0 - 1048.0) / 1048.0 * 100)


def test_equity_curve_marks_open_position_to_market_at_end():
    analyzer = PerformanceAnalyzer()
    curve = analyzer.generate_equity_curve(
        [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        [100.0, 110.0, 120.0],
        [
            {
                "symbol": "TEST",
                "entry_date": date(2026, 1, 1),
                "quantity": 5,
                "entry_price": 100.0,
                "entry_commission": 2.0,
            }
        ],
        1000.0,
    )

    assert curve[-1]["cash"] == 498.0
    assert curve[-1]["holdings_value"] == 600.0
    assert curve[-1]["equity"] == 1098.0
    assert curve[-1]["drawdown_pct"] == 0.0


def test_equity_curve_does_not_execute_trade_when_cash_is_insufficient():
    analyzer = PerformanceAnalyzer()
    curve = analyzer.generate_equity_curve(
        [date(2026, 1, 1), date(2026, 1, 2)],
        [100.0, 110.0],
        [
            {
                "symbol": "TEST",
                "entry_date": date(2026, 1, 1),
                "quantity": 20,
                "entry_price": 100.0,
            }
        ],
        1000.0,
    )

    assert all(point["equity"] == 1000.0 for point in curve)
    assert all(point["holdings_value"] == 0.0 for point in curve)


def test_equity_curve_rejects_mismatched_price_series():
    analyzer = PerformanceAnalyzer()

    with pytest.raises(ValueError, match="same length"):
        analyzer.generate_equity_curve(
            [date(2026, 1, 1), date(2026, 1, 2)],
            [100.0],
            [],
            1000.0,
        )
