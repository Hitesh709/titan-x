from __future__ import annotations

from typing import Any


TOTAL_POINTS = 100.0


def calculate_titan_score(evidence: dict[str, Any]) -> dict[str, Any]:
    """Calculate a deterministic, explainable 0-100 TITAN X score.

    Missing evidence earns zero points and reduces coverage. This prevents a
    partially populated stock record from looking artificially strong.
    """
    points = 0.0
    available_points = 0.0
    reasons: list[str] = []

    for key, weight, reason in (
        ("price_above_sma20", 10.0, "Price above SMA20"),
        ("price_above_sma50", 10.0, "Price above SMA50"),
        ("price_above_sma200", 10.0, "Price above SMA200"),
    ):
        value = evidence.get(key)
        if value is not None:
            available_points += weight
            if value:
                points += weight
                reasons.append(reason)

    rsi = evidence.get("rsi")
    if rsi is not None:
        available_points += 15.0
        value = float(rsi)
        if 50 <= value <= 70:
            points += 15.0
            reasons.append(f"RSI supportive ({value:.1f})")
        elif 45 <= value < 50:
            points += 7.5

    macd_bullish = evidence.get("macd_bullish")
    if macd_bullish is not None:
        available_points += 10.0
        if macd_bullish:
            points += 10.0
            reasons.append("MACD bullish")

    volume_ratio = evidence.get("volume_ratio")
    if volume_ratio is not None:
        available_points += 15.0
        ratio = float(volume_ratio)
        if ratio >= 1.5:
            points += 15.0
            reasons.append(f"Volume breakout ({ratio:.2f}x average)")
        elif ratio >= 1.0:
            points += 10.0

    roe = evidence.get("roe")
    if roe is not None:
        available_points += 10.0
        value = float(roe)
        if value >= 15:
            points += 10.0
            reasons.append(f"ROE strong ({value:.1f}%)")
        elif value >= 10:
            points += 5.0

    pe = evidence.get("pe_ratio")
    if pe is not None and float(pe) > 0:
        available_points += 10.0
        value = float(pe)
        if value <= 25:
            points += 10.0
            reasons.append(f"PE reasonable ({value:.1f})")
        elif value <= 40:
            points += 5.0

    ai_score = evidence.get("ai_score")
    if ai_score is not None:
        available_points += 10.0
        normalized = max(0.0, min(100.0, float(ai_score))) / 100.0
        points += normalized * 10.0
        if normalized >= 0.8:
            reasons.append(f"AI score strong ({float(ai_score):.1f})")

    return {
        "score": round(min(TOTAL_POINTS, points), 2),
        "points": round(points, 2),
        "maximum_points": TOTAL_POINTS,
        "coverage_pct": round(available_points / TOTAL_POINTS * 100.0, 2),
        "reasons": reasons,
    }
