from datetime import date, timedelta

import pytest

from titan_x.services.advanced_strategy_engine import AdvancedStrategyEngine


def _prices(n=70):
    rows = []
    for i in range(n):
        close = 100 + i * 0.8
        rows.append({"date": date(2025, 1, 1) + timedelta(days=i), "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000})
    return rows


def test_advanced_engine_generates_confirmed_signals():
    signals = AdvancedStrategyEngine().generate_signals(_prices())
    assert signals
    assert all(s["signal_type"] == "advanced_multi_indicator" for s in signals)
    assert all(0 <= s["confidence"] <= 1 for s in signals)


def test_risk_metadata_is_attached_to_entries():
    signals = AdvancedStrategyEngine().generate_signals(_prices(), {"stop_loss_pct": 1.5, "take_profit_pct": 5.0})
    entries = [s for s in signals if s["action"] == "buy"]
    assert entries
    assert entries[0]["stop_loss_pct"] == 1.5
    assert entries[0]["take_profit_pct"] == 5.0


def test_invalid_periods_are_rejected():
    with pytest.raises(ValueError):
        AdvancedStrategyEngine().generate_signals(_prices(), {"fast_period": 30, "slow_period": 10})


def test_invalid_trailing_stop_is_rejected():
    with pytest.raises(ValueError):
        AdvancedStrategyEngine.validate_params({"trailing_stop_pct": 0})
