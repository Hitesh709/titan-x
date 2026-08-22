"""Sprint 1 regression tests for the canonical screener contract.

These tests are intentionally dependency-light. They protect the pure rules
that must remain true even when the database/API implementation changes:
- true Golden/Death Cross semantics;
- point-in-time filtering;
- transparent TITAN X score bounds and missing-data handling.
"""

from datetime import date


def sma_cross(previous_fast: float, previous_slow: float, current_fast: float, current_slow: float, kind: str) -> bool:
    if kind == "golden":
        return previous_fast <= previous_slow and current_fast > current_slow
    if kind == "death":
        return previous_fast >= previous_slow and current_fast < current_slow
    raise ValueError("kind must be golden or death")


def latest_point_in_time(records: list[dict], as_of: date | None) -> dict | None:
    eligible = [r for r in records if as_of is None or r["published_at"] <= as_of]
    return max(eligible, key=lambda r: r["published_at"]) if eligible else None


def titan_x_score(*, trend: float | None = None, momentum: float | None = None,
                  fundamental: float | None = None, ai: float | None = None) -> dict:
    components = {
        "trend": (trend, 30.0),
        "momentum": (momentum, 25.0),
        "fundamental": (fundamental, 20.0),
        "ai": (ai, 10.0),
    }
    score = 0.0
    maximum = 0.0
    reasons: list[str] = []
    for name, (value, weight) in components.items():
        if value is None:
            continue
        score += max(0.0, min(1.0, value)) * weight
        maximum += weight
        if value >= 0.7:
            reasons.append(name)
    return {"score": round(score, 2), "maximum": maximum, "reasons": reasons}


def test_golden_cross_requires_an_actual_cross() -> None:
    assert sma_cross(99, 100, 101, 100, "golden")
    assert not sma_cross(101, 100, 102, 100, "golden")


def test_death_cross_requires_an_actual_cross() -> None:
    assert sma_cross(101, 100, 99, 100, "death")
    assert not sma_cross(99, 100, 98, 100, "death")


def test_point_in_time_fundamental_never_uses_future_filing() -> None:
    records = [
        {"published_at": date(2025, 3, 31), "value": 10},
        {"published_at": date(2025, 6, 30), "value": 20},
    ]
    selected = latest_point_in_time(records, date(2025, 5, 1))
    assert selected == records[0]


def test_point_in_time_returns_latest_available_record() -> None:
    records = [
        {"published_at": date(2025, 3, 31), "value": 10},
        {"published_at": date(2025, 6, 30), "value": 20},
    ]
    selected = latest_point_in_time(records, date(2025, 12, 31))
    assert selected == records[1]


def test_titan_x_score_is_bounded_and_transparent() -> None:
    result = titan_x_score(trend=1.0, momentum=1.0, fundamental=1.0, ai=1.0)
    assert 0 <= result["score"] <= 100
    assert result["score"] == 85
    assert set(result["reasons"]) == {"trend", "momentum", "fundamental", "ai"}


def test_titan_x_score_handles_missing_data_without_fabricating_it() -> None:
    result = titan_x_score(trend=0.8, momentum=None, fundamental=None, ai=None)
    assert result["score"] == 24
    assert result["maximum"] == 30
    assert result["reasons"] == ["trend"]
