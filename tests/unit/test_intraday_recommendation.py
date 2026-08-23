from titan_x.services.intraday_recommendation_service import _score_intraday


def _bars(count: int = 80):
    from titan_x.services.ai_recommendation_engine import Bar

    rows = []
    price = 100.0
    for i in range(count):
        price += 0.35 if i < count - 8 else 0.15
        rows.append(
            {
                "trade_date": f"2026-08-{(i % 28) + 1:02d}",
                "open": price - 0.10,
                "high": price + 0.25,
                "low": price - 0.20,
                "close": price,
                "volume": 100000 + (25000 if i >= count - 3 else 0),
            }
        )
    return rows


def test_intraday_score_produces_valid_trade_levels():
    result = _score_intraday(_bars())
    assert result is not None
    assert result["direction"] in {"BUY", "SELL", "HOLD"}
    assert 0 <= result["score"] <= 100
    assert 0 <= result["confidence"] <= 95
    assert result["current_price"] > 0
    assert result["entry_price"] > 0
    assert result["target_price"] >= 0
    assert result["stop_price"] >= 0
    assert result["volume_ratio"] > 0


def test_intraday_rejects_insufficient_history():
    assert _score_intraday(_bars(20)) is None
