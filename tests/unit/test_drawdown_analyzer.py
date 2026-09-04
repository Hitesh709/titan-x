from datetime import date, timedelta

from titan_x.services.drawdown_analyzer import DrawdownAnalyzer


def curve(values: list[float]) -> list[dict]:
    start = date(2026, 1, 1)
    return [{"date": start + timedelta(days=i), "equity": value} for i, value in enumerate(values)]


def test_drawdown_peak_trough_and_recovery():
    result = DrawdownAnalyzer().analyze(curve([100, 110, 90, 95, 110, 120]))

    assert result["max_drawdown"] == 20
    assert result["max_drawdown_pct"] == 18.181818181818183
    assert result["peak_date"] == date(2026, 1, 2)
    assert result["trough_date"] == date(2026, 1, 3)
    assert result["recovery_date"] == date(2026, 1, 5)
    assert result["recovery_days"] == 2


def test_drawdown_recovery_period():
    result = DrawdownAnalyzer().analyze(curve([100, 120, 100, 90, 120, 130]))

    assert result["max_drawdown"] == 30
    assert result["max_drawdown_pct"] == 25
    assert result["peak_date"] == date(2026, 1, 2)
    assert result["trough_date"] == date(2026, 1, 4)
    assert result["recovery_date"] == date(2026, 1, 5)
    assert result["recovery_days"] == 1


def test_no_drawdown():
    result = DrawdownAnalyzer().analyze(curve([100, 101, 102, 105]))

    assert result["max_drawdown"] == 0
    assert result["max_drawdown_pct"] == 0
    assert result["peak_date"] is None
    assert result["trough_date"] is None


def test_empty_curve():
    result = DrawdownAnalyzer().analyze([])

    assert result["max_drawdown"] == 0
    assert result["duration_days"] == 0
    assert result["recovery_days"] is None
