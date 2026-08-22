from titan_x.services.screener_scoring import calculate_titan_score


def test_titan_score_is_transparent_and_bounded():
    result = calculate_titan_score({
        "price_above_sma20": True,
        "price_above_sma50": True,
        "price_above_sma200": True,
        "rsi": 62,
        "macd_bullish": True,
        "volume_ratio": 1.8,
        "roe": 19,
        "pe_ratio": 22,
        "ai_score": 90,
    })

    assert 0 <= result["score"] <= 100
    assert result["score"] > 90
    assert result["coverage_pct"] == 100
    assert result["reasons"]


def test_missing_evidence_is_conservative():
    result = calculate_titan_score({"rsi": 55})

    assert result["score"] == 15
    assert result["coverage_pct"] == 15
    assert result["maximum_points"] == 100


def test_weak_evidence_does_not_receive_full_points():
    result = calculate_titan_score({
        "price_above_sma20": False,
        "price_above_sma50": False,
        "price_above_sma200": False,
        "rsi": 80,
        "macd_bullish": False,
        "volume_ratio": 0.7,
        "roe": 5,
        "pe_ratio": 70,
        "ai_score": 20,
    })

    assert result["score"] < 10
