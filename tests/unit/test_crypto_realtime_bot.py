from titan_x.services.crypto_realtime_bot import _signal


def _candles(count: int, *, start: float = 100.0, step: float = 1.0, closed: bool = True):
    return [
        {
            "open": start + i * step,
            "high": start + i * step + 1,
            "low": start + i * step - 1,
            "close": start + i * step,
            "volume": 100.0,
            "closed": closed,
        }
        for i in range(count)
    ]


def test_realtime_bot_ignores_unclosed_candle():
    confirmed = _candles(60)
    baseline = _signal(confirmed)

    # A dramatic live-candle move must not alter a decision until that candle closes.
    active = _candles(1, start=10_000.0, closed=False)[0]
    decision_with_active_candle = _signal(confirmed + [active])

    assert baseline[0] == "BUY"
    assert decision_with_active_candle == baseline


def test_realtime_bot_waits_for_60_confirmed_candles():
    candles = _candles(59) + _candles(1, start=10_000.0, closed=False)
    assert _signal(candles) == ("HOLD", 0.0, 0.0)
