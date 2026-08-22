from datetime import date, timedelta

from titan_x.services.backtest_engine import BacktestEngine


def _engine() -> BacktestEngine:
    return BacktestEngine.__new__(BacktestEngine)


def _prices(closes: list[float]) -> list[dict]:
    start = date(2025, 1, 1)
    return [
        {"date": start + timedelta(days=i), "open": close, "high": close, "low": close, "close": close, "volume": 1000}
        for i, close in enumerate(closes)
    ]


def test_sma_indicator_and_crossover_strategy() -> None:
    engine = _engine()
    prices = _prices([10, 10, 10, 10, 9, 8, 9, 11, 13, 14])
    indicators = engine._compute_indicators(prices, "sma_crossover", {"fast_period": 2, "slow_period": 4})

    assert indicators["sma_fast"][0] is None
    assert indicators["sma_slow"][2] is None
    assert indicators["sma_slow"][3] == 10
    signals = engine._generate_signals(prices, indicators, "sma_crossover", {"fast_period": 2, "slow_period": 4})
    assert any(signal["action"] == "buy" for signal in signals)


def test_rsi_strategy_generates_crossing_signals() -> None:
    engine = _engine()
    closes = [100, 98, 96, 94, 92, 90, 92, 94, 96, 98, 100, 102, 104, 106, 108, 110, 108, 106, 104]
    prices = _prices(closes)
    indicators = engine._compute_indicators(prices, "rsi", {"rsi_period": 5})
    signals = engine._generate_signals(
        prices,
        indicators,
        "rsi",
        {"rsi_period": 5, "oversold": 30, "overbought": 70},
    )
    assert all(signal["signal_type"].startswith("rsi_") for signal in signals)


def test_bollinger_strategy_generates_valid_signal_shape() -> None:
    engine = _engine()
    closes = [100 + ((i % 5) - 2) for i in range(30)] + [80]
    prices = _prices(closes)
    indicators = engine._compute_indicators(prices, "bollinger", {"bb_period": 20, "bb_std": 2.0})
    signals = engine._generate_signals(prices, indicators, "bollinger", {"bb_period": 20, "bb_std": 2.0})
    assert all(signal["action"] in {"buy", "sell"} for signal in signals)
    assert all("signal_date" in signal and "price" in signal for signal in signals)


def test_custom_strategy_accepts_explicit_signals() -> None:
    engine = _engine()
    prices = _prices([100, 101, 102])
    indicators = engine._compute_indicators(prices, "custom", {})
    signals = engine._generate_signals(
        prices,
        indicators,
        "custom",
        {
            "signals": [
                {"date": "2025-01-02", "action": "buy", "price": 101, "confidence": 0.8},
                {"date": "2025-01-03", "action": "sell", "price": 102, "confidence": 0.9},
            ]
        },
    )
    assert len(signals) == 2
    assert signals[0]["action"] == "buy"
    assert signals[1]["action"] == "sell"
