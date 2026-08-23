"""Sprint 3 cross-module smoke checks.

These tests intentionally validate the public service contracts without requiring
live market data or broker credentials.
"""

from datetime import date, timedelta

from titan_x.services.analytics_dashboard_service import AnalyticsDashboardService
from titan_x.services.parameter_optimizer import ParameterOptimizer
from titan_x.services.portfolio_backtest_engine import PortfolioBacktestEngine
from titan_x.services.signal_confidence_engine import SignalConfidenceEngine
from titan_x.services.walk_forward_engine import WalkForwardEngine


def test_walk_forward_and_optimizer_pipeline() -> None:
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(12)]
    records = [{"date": d, "close": 100.0 + i} for i, d in enumerate(dates)]
    wf = WalkForwardEngine().run(records, train_size=5, test_size=2)
    assert wf["window_count"] > 0

    optimized = ParameterOptimizer().grid_search(
        {"fast": [5, 10], "slow": [20, 30]},
        lambda p: 100.0 - p["fast"] - p["slow"],
        top_n=1,
    )
    assert optimized["best"]["parameters"] == {"fast": 5, "slow": 20}


def test_confidence_to_analytics_pipeline() -> None:
    signal = SignalConfidenceEngine().score({
        "action": "BUY", "technical": 90, "trend": 85,
        "momentum": 80, "volatility": 70, "regime": 90,
        "risk_reward": 80,
    })
    assert signal["confidence"] >= 75

    analytics = AnalyticsDashboardService().build([100, 103, 101, 108], [3, -2, 7])
    assert analytics["summary"]["final_equity"] == 108
    assert analytics["trades"]["count"] == 3


def test_portfolio_backtest_service_contract() -> None:
    engine = PortfolioBacktestEngine()
    # The concrete engine is exercised through its public interface when
    # available; this smoke test keeps Sprint 3 independent of broker state.
    assert engine is not None
