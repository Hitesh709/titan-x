from __future__ import annotations

from typing import Any


def calculate_titan_score(evidence: dict[str, Any]) -> dict[str, Any]:
    """Calculate a transparent 0-100 screener score from available evidence.

    The score is deliberately deterministic and explainable. Missing evidence
    does not receive points and is reported through coverage, preventing the
    score from pretending that unavailable data was evaluated.
    """
    points = 0.0
    maximum = 0.0
    reasons: list[str] = []

    # Trend: 30 points
    trend_checks = (
        ("price_above_sma20", 10.0, "Price above SMA20"),
        ("price_above_sma50", 10.0, "Price above SMA50"),
        ("price_above_sma200", 10.0, "Price above SMA200"),
    )
    for key, weight, reason in trend_checks:
        value = evidence.get(key)
        if value is not None:
            maximum += weight
            if value:
                points += weight
                reasons.append(reason)

    # Momentum: 25 points
    rsi = evidence.get("rsi")
    if rsi is not None:
        maximum += 15.0
        if 50 <= float(rsi) <= 70:
            points += 15.0
            reasons.append(f"RSI supportive ({float(rsi):.1f})")
        elif 45 <= float(rsi) < 50:
            points += 7.5

    macd_bullish = evidence.get("macd_bullish")
    if macd_bullish is not None:
        maximum += 10.0
        if macd_bullish:
            points += 10.0
            reasons.append("MACD bullish")

    # Volume: 15 points
    volume_ratio = evidence.get("volume_ratio")
    if volume_ratio is not None:
        maximum += 15.0
        ratio = float(volume_ratio)
        if ratio >= 1.5:
            points += 15.0
            reasons.append(f"Volume breakout ({ratio:.2f}x average)")
        elif ratio >= 1.0:
            points += 10.0

    # Fundamentals: 20 points
    roe = evidence.get("roe")
    if roe is not None:
        maximum += 10.0
        if float(roe) >= 15:
            points += 10.0
            reasons.append(f"ROE strong ({float(roe):.1f}%)")
        elif float(roe) >= 10:
            points += 5.0

    pe = evidence.get("pe_ratio")
    if pe is not None and float(pe) > 0:
        maximum += 10.0
        if float(pe) <= 25:
            points += 10.0
            reasons.append(f"PE reasonable ({float(pe):.1f})")
        elif float(pe) <= 40:
            points += 5.0

    # AI evidence: 10 points
    ai_score = evidence.get("ai_score")
    if ai_score is not None:
        maximum += 10.0
        normalized = max(0.0, min(100.0, float(ai_score))) / 100.0
        points += normalized * 10.0
        if normalized >= 0.8:
            reasons.append(f"AI score strong ({float(ai_score):.1f})")

    score = round(points / maximum * 100.0, 2) if maximum else 0.0
    return {
        "score": score,
        "points": round(points, 2),
        "maximum_points": round(maximum, 2),
        "coverage_pct": round(maximum, 2),
        "reasons": reasons,
    }
