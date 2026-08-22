from datetime import date

import pytest

from titan_x.services.backtest_engine import BacktestEngine


def test_buy_signal_executes_on_next_bar_open_not_signal_close() -> None:
    engine = BacktestEngine.__new__(BacktestEngine)
    prices = [
        {"date": date(2025, 1, 1), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"date": date(2025, 1, 2), "open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0, "volume": 1000},
        {"date": date(2025, 1, 3), "open": 120.0, "high": 121.0, "low": 119.0, "close": 120.0, "volume": 1000},
    ]
    signals = [{
        "signal_date": date(2025, 1, 1), "action": "buy", "price": 100.0,
        "signal_type": "test_buy", "confidence": 1.0,
    }]

    trades, _ = engine._simulate_trades(prices, signals, 10000.0, 0.0, 0.0, "capital_pct", 0.95)

    assert trades
    assert trades[0]["entry_date"] == date(2025, 1, 2)
    assert trades[0]["entry_price"] == 110.0
    assert trades[0]["entry_date"] != signals[0]["signal_date"]


def test_sell_signal_executes_on_next_bar_open() -> None:
    engine = BacktestEngine.__new__(BacktestEngine)
    prices = [
        {"date": date(2025, 1, 1), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"date": date(2025, 1, 2), "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1000},
        {"date": date(2025, 1, 3), "open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0, "volume": 1000},
        {"date": date(2025, 1, 4), "open": 80.0, "high": 81.0, "low": 79.0, "close": 80.0, "volume": 1000},
    ]
    signals = [
        {"signal_date": date(2025, 1, 1), "action": "buy", "price": 100.0, "signal_type": "test_buy"},
        {"signal_date": date(2025, 1, 2), "action": "sell", "price": 101.0, "signal_type": "test_sell"},
    ]

    trades, _ = engine._simulate_trades(prices, signals, 10000.0, 0.0, 0.0, "capital_pct", 0.95)

    closed = next(t for t in trades if t["status"] == "closed")
    assert closed["entry_date"] == date(2025, 1, 2)
    assert closed["exit_date"] == date(2025, 1, 3)
    assert closed["exit_price"] == 90.0


def test_execution_delay_can_be_configured_beyond_one_bar() -> None:
    engine = BacktestEngine.__new__(BacktestEngine)
    prices = [
        {"date": date(2025, 1, 1), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"date": date(2025, 1, 2), "open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0, "volume": 1000},
        {"date": date(2025, 1, 3), "open": 120.0, "high": 121.0, "low": 119.0, "close": 120.0, "volume": 1000},
        {"date": date(2025, 1, 4), "open": 130.0, "high": 131.0, "low": 129.0, "close": 130.0, "volume": 1000},
    ]
    signals = [{"signal_date": date(2025, 1, 1), "action": "buy", "price": 100.0, "signal_type": "test_buy"}]

    trades, _ = engine._simulate_trades(prices, signals, 10000.0, 0.0, 0.0, "capital_pct", 0.95, 2)

    assert trades
    assert trades[0]["entry_date"] == date(2025, 1, 3)
    assert trades[0]["entry_price"] == 120.0


def test_signal_on_last_bar_is_not_executed_after_backtest_window() -> None:
    engine = BacktestEngine.__new__(BacktestEngine)
    prices = [
        {"date": date(2025, 1, 1), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"date": date(2025, 1, 2), "open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0, "volume": 1000},
    ]
    signals = [{"signal_date": date(2025, 1, 2), "action": "buy", "price": 111.0, "signal_type": "last_bar_buy"}]

    trades, _ = engine._simulate_trades(prices, signals, 10000.0, 0.0, 0.0, "capital_pct", 0.95)

    assert trades == []


def test_zero_execution_delay_is_rejected() -> None:
    engine = BacktestEngine.__new__(BacktestEngine)
    prices = [
        {"date": date(2025, 1, 1), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"date": date(2025, 1, 2), "open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0, "volume": 1000},
    ]
    signals = [{"signal_date": date(2025, 1, 1), "action": "buy", "price": 100.0, "signal_type": "invalid_delay"}]

    with pytest.raises(ValueError, match="execution_delay_bars"):
        engine._simulate_trades(prices, signals, 10000.0, 0.0, 0.0, "capital_pct", 0.95, 0)
