import pytest

from titan_x.services.analytics_dashboard_service import AnalyticsDashboardService


def test_builds_full_analytics_snapshot() -> None:
    result = AnalyticsDashboardService().build(
        [100, 105, 102, 110],
        [5, -3, 8, -1],
        benchmark_return_pct=5.0,
    )
    assert result["summary"]["total_return_pct"] == pytest.approx(10.0)
    assert result["summary"]["max_drawdown_pct"] == pytest.approx(-2.8571, abs=1e-4)
    assert result["trades"]["count"] == 4
    assert result["trades"]["win_rate_pct"] == 50.0
    assert result["benchmark"]["alpha_pct"] == pytest.approx(5.0)
    assert len(result["equity_curve"]) == 4
    assert len(result["drawdown_curve"]) == 4


def test_empty_equity_is_rejected() -> None:
    with pytest.raises(ValueError):
        AnalyticsDashboardService().build([], [])
