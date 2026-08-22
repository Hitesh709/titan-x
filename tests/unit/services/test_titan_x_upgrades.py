from datetime import date

import pytest

from titan_x.services.advanced_screener_service_v2 import ProductionScreenerService
from titan_x.services.backtest_engine_v2 import ProductionBacktestEngine


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return _Result(self.rows)


def _engine_without_init(cls):
    return object.__new__(cls)


@pytest.mark.asyncio
async def test_true_golden_cross_requires_an_actual_cross():
    engine = _engine_without_init(ProductionScreenerService)
    engine._session = _Session([
        ("ABC.NS", 20, 101.0, date(2026, 1, 10)),
        ("ABC.NS", 20, 99.0, date(2026, 1, 9)),
        ("ABC.NS", 50, 100.0, date(2026, 1, 10)),
        ("ABC.NS", 50, 100.0, date(2026, 1, 9)),
    ])

    result = await engine._filter_true_sma_cross(
        {"fast": 20, "slow": 50, "type": "golden"},
        date(2026, 1, 10),
    )

    assert result == {"ABC.NS"}


@pytest.mark.asyncio
async def test_true_cross_does_not_compare_different_previous_dates():
    engine = _engine_without_init(ProductionScreenerService)
    engine._session = _Session([
        ("ABC.NS", 20, 101.0, date(2026, 1, 10)),
        ("ABC.NS", 20, 99.0, date(2026, 1, 9)),
        ("ABC.NS", 50, 100.0, date(2026, 1, 10)),
        ("ABC.NS", 50, 100.0, date(2026, 1, 8)),
    ])

    result = await engine._filter_true_sma_cross(
        {"fast": 20, "slow": 50, "type": "golden"},
        date(2026, 1, 10),
    )

    assert result == set()


def test_backtest_signal_executes_on_next_bar_open():
    engine = _engine_without_init(ProductionBacktestEngine)
    prices = [
        {"date": date(2026, 1, 1), "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000},
        {"date": date(2026, 1, 2), "open": 110, "high": 112, "low": 109, "close": 111, "volume": 1000},
        {"date": date(2026, 1, 3), "open": 120, "high": 121, "low": 119, "close": 120, "volume": 1000},
    ]
    signals = [
        {"signal_date": date(2026, 1, 1), "symbol": "ABC.NS", "action": "buy", "signal_type": "test"},
        {"signal_date": date(2026, 1, 2), "symbol": "ABC.NS", "action": "sell", "signal_type": "test"},
    ]

    trades, curve = engine._simulate_trades(
        prices,
        signals,
        initial_capital=100000,
        commission_pct=0.0,
        slippage_pct=0.0,
        position_sizing="capital_pct",
        position_value_pct=1.0,
    )

    assert len(trades) == 1
    assert trades[0]["entry_date"] == date(2026, 1, 2)
    assert trades[0]["entry_price"] == 110
    assert trades[0]["exit_date"] == date(2026, 1, 3)
    assert trades[0]["exit_price"] == 120
    assert curve[-1]["equity"] > 100000
