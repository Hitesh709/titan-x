from datetime import date

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
    assert result["avg_drawdown"] == 100.0
    assert result["avg_drawdown_pct"] == 10.0


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
