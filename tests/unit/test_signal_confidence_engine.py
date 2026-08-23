import pytest

from titan_x.services.signal_confidence_engine import SignalConfidenceEngine


def test_scores_and_classifies_signal() -> None:
    result = SignalConfidenceEngine().score({
        "action": "BUY",
        "technical": 90,
        "trend": 85,
        "momentum": 80,
        "volatility": 70,
        "regime": 90,
        "risk_reward": 80,
    })
    assert result["action"] == "BUY"
    assert 0 <= result["confidence"] <= 100
    assert result["label"] == "STRONG"
    assert set(result["factors"]) == {
        "technical", "trend", "momentum", "volatility", "regime", "risk_reward"
    }


def test_clamps_factors_and_handles_hold() -> None:
    result = SignalConfidenceEngine().score({"action": "HOLD", "technical": 150, "trend": -20})
    assert result["action"] == "HOLD"
    assert result["factors"]["technical"] == 100
    assert result["factors"]["trend"] == 0


def test_rejects_invalid_action_and_non_numeric_factor() -> None:
    with pytest.raises(ValueError):
        SignalConfidenceEngine().score({"action": "LONG"})
    with pytest.raises(ValueError):
        SignalConfidenceEngine().score({"action": "BUY", "technical": "bad"})
