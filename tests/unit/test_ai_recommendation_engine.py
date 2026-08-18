"""Unit tests for the selective, 6-pillar AI recommendation engine.

These tests are fully offline: they feed synthetic OHLCV / fundamentals / news
and assert (a) a decisively bullish setup produces an actionable STRONG BUY,
(b) weak / disagreeing setups are rejected with NO-TRADE, and
(c) the explainability payload is complete and self-documenting.
"""
import random
from datetime import date

import pytest

from titan_x.services.ai_recommendation_engine import (
    AIRecommendationEngine,
    Bar,
    Fundamentals,
    MarketRegime,
    NewsItem,
    bars_from_records,
    fundamentals_from_records,
    news_from_records,
)


def _trend_bars(n: int = 200, drift: float = 0.0025, vol: float = 0.001, start: float = 100.0):
    bars = []
    base = date(2024, 1, 1).toordinal()
    p = start
    for i in range(n):
        p *= (1 + drift + vol * ((i % 5) - 2) * 0.1)
        bars.append(
            Bar(
                trade_date=date.fromordinal(base + i),
                open=p,
                high=p * 1.02,
                low=p * 0.98,
                close=p,
                volume=2_000_000,
            )
        )
    return bars


def _rand_bars(n: int = 120, seed: int = 1):
    random.seed(seed)
    bars = []
    base = date(2024, 1, 1).toordinal()
    p = 100.0
    for i in range(n):
        p *= 1 + random.uniform(-0.01, 0.012)
        bars.append(
            Bar(
                trade_date=date.fromordinal(base + i),
                open=p,
                high=p * 1.01,
                low=p * 0.99,
                close=p,
                volume=1_000_000,
            )
        )
    return bars


def _bull_fundamentals():
    return Fundamentals(
        revenue_growth_yoy=28, eps_growth_yoy=25, roe=30, roce=28,
        debt_to_equity=0.2, net_margin=25, pe_ratio=22, promoter_holding=65,
    )


def _bull_news():
    return [
        NewsItem(sentiment_label="positive", sentiment_score=0.8, impact=0.6, confidence=0.8),
        NewsItem(sentiment_label="positive", sentiment_score=0.5, impact=0.4, confidence=0.7),
    ]


def _bull_regime():
    return MarketRegime(nifty_trend=80, sector_momentum=85, india_vix=11,
                        breadth_adv_decl=1.5, fii_dii_net=10)


# --------------------------------------------------------------------------- #
def test_strong_bullish_setup_produces_actionable_signal():
    eng = AIRecommendationEngine()
    rec = eng.build(
        "TSTR", _trend_bars(),
        fundamentals=_bull_fundamentals(), news=_bull_news(), regime=_bull_regime(),
    )
    assert rec["no_trade"] is False
    assert rec["signal"] in ("buy", "strong_buy")
    assert rec["direction"] == "BUY"
    assert rec["score"] >= 82.0
    assert rec["calibrated_probability"] >= 0.75
    assert rec["entry_price"] > 0
    assert rec["stop_price"] < rec["entry_price"] < rec["price_target"]
    assert rec["risk_reward"] >= 2.0
    assert rec["explainability"]["conviction"] in ("STRONG", "HIGH")


def test_weak_random_setup_is_no_trade():
    eng = AIRecommendationEngine()
    rec = eng.build("WK", _rand_bars(seed=1))
    assert rec["no_trade"] is True
    assert rec["signal"] == "hold"
    assert rec["rejection_reasons"]
    assert ("weak_probability" in rec["rejection_reasons"]
            or "insufficient_confident_models" in rec["rejection_reasons"])


def test_disagreement_is_no_trade():
    eng = AIRecommendationEngine()
    bars = _trend_bars(drift=0.0025)
    rec = eng.build(
        "DIS", bars,
        fundamentals=Fundamentals(revenue_growth_yoy=-20, eps_growth_yoy=-25, roe=-10,
                                  debt_to_equity=2.5, net_margin=-10, pe_ratio=120),
        regime=MarketRegime(nifty_trend=15, sector_momentum=10, india_vix=30,
                            breadth_adv_decl=0.4, fii_dii_net=-15),
    )
    assert rec["no_trade"] is True


def test_insufficient_price_data_is_no_trade():
    eng = AIRecommendationEngine()
    rec = eng.build("SHORT", _trend_bars(n=20))
    assert rec["no_trade"] is True
    assert rec["insufficient_data"] is True
    assert "insufficient_price_data" in rec["rejection_reasons"]


def test_explainability_is_complete():
    eng = AIRecommendationEngine()
    rec = eng.build(
        "EX", _trend_bars(),
        fundamentals=_bull_fundamentals(), news=_bull_news(), regime=_bull_regime(),
    )
    exp = rec["explainability"]
    for key in ("symbol", "signal", "conviction", "score", "calibrated_probability",
                "entry", "target", "stop", "risk_reward", "model_agreement",
                "pillars", "historical_evidence", "reasons", "risks", "disclaimer"):
        assert key in exp, f"missing {key}"
    assert len(exp["pillars"]) == 6
    assert "Not investment advice" in exp["disclaimer"]
    assert "No guaranteed accuracy" in exp["disclaimer"]


def test_record_converters():
    dicts = [{"trade_date": date(2025, 1, 1), "open": 1, "high": 2, "low": 0.5,
              "close": 100.0, "volume": 1e6}]
    bars = bars_from_records(dicts)
    assert bars[0].close == 100.0 and bars[0].volume == 1e6

    class M:
        def __init__(self, n, v):
            self.metric_name = n
            self.value = v

    f = fundamentals_from_records([M("roe", 22), M("pe_ratio", 18)])
    assert f.roe == 22 and f.pe_ratio == 18

    class N:
        sentiment_label = "negative"
        sentiment_positive = 0.1
        sentiment_negative = 0.7
        sentiment_confidence = 0.6
        event_confidence = 0.5

    class A:
        title = "Bad"
        nlp_analysis = N()

    items = news_from_records([A()])
    assert items[0].sentiment_score == pytest.approx(-0.6)
