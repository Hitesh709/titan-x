from datetime import date

from titan_x.services.performance_analyzer import PerformanceAnalyzer


def test_equity_curve_marks_open_position_to_market() -> None:
    analyzer = PerformanceAnalyzer()
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    closes = [100.0, 110.0, 120.0]
    trades = [
        {
            "entry_date": dates[0],
            "entry_price": 100.0,
            "quantity": 10.0,
            "commission": 0.0,
            "exit_date": None,
            "exit_price": None,
        }
    ]

    curve = analyzer.generate_equity_curve(dates, closes, trades, 1000.0)

    assert len(curve) == 3
    assert curve[0]["equity"] == 1000.0
    assert curve[-1]["equity"] == 1200.0
    assert curve[-1]["holdings_value"] == 1200.0
    assert curve[-1]["drawdown_pct"] == 0.0


def test_equity_curve_realizes_exit_and_tracks_drawdown() -> None:
    analyzer = PerformanceAnalyzer()
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    closes = [100.0, 80.0, 90.0]
    trades = [
        {
            "entry_date": dates[0],
            "entry_price": 100.0,
            "quantity": 5.0,
            "commission": 0.0,
            "exit_date": dates[2],
            "exit_price": 90.0,
        }
    ]

    curve = analyzer.generate_equity_curve(dates, closes, trades, 1000.0)

    assert len(curve) == 3
    assert curve[1]["equity"] == 900.0
    assert curve[1]["drawdown_pct"] == 10.0
    assert curve[-1]["equity"] == 950.0
    assert curve[-1]["holdings_value"] == 0.0


def test_equity_curve_rejects_mismatched_price_series() -> None:
    analyzer = PerformanceAnalyzer()

    try:
        analyzer.generate_equity_curve(
            [date(2026, 1, 1)],
            [100.0, 101.0],
            [],
            1000.0,
        )
    except ValueError as exc:
        assert "same length" in str(exc)
    else:
        raise AssertionError("Expected ValueError for mismatched price series")
