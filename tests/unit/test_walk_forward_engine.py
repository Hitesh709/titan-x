from datetime import date, timedelta

import pytest

from titan_x.services.walk_forward_engine import WalkForwardEngine


def _dates(n: int) -> list[date]:
    start = date(2026, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def test_generates_non_overlapping_out_of_sample_windows() -> None:
    engine = WalkForwardEngine()
    windows = engine.generate_windows(_dates(10), train_size=4, test_size=2)
    assert len(windows) == 3
    assert windows[0].train_end < windows[0].test_start
    assert windows[1].train_start == date(2026, 1, 7)


def test_supports_rolling_step() -> None:
    engine = WalkForwardEngine()
    windows = engine.generate_windows(_dates(8), 3, 2, step_size=1)
    assert len(windows) == 4


def test_rejects_unsorted_dates() -> None:
    engine = WalkForwardEngine()
    dates = _dates(6)
    dates[2], dates[3] = dates[3], dates[2]
    with pytest.raises(ValueError, match="strictly increasing"):
        engine.generate_windows(dates, 3, 2)


def test_run_returns_out_of_sample_count_and_metrics() -> None:
    engine = WalkForwardEngine()
    records = [{"date": d, "close": 100 + i} for i, d in enumerate(_dates(7))]
    result = engine.run(
        records,
        train_size=3,
        test_size=2,
        train_evaluator=lambda rows: 1.0,
        test_evaluator=lambda rows: 2.0,
    )
    assert result["window_count"] == 2
    assert result["out_of_sample_count"] == 4
    assert all(w["train_return_pct"] == 1.0 for w in result["windows"])
    assert all(w["test_return_pct"] == 2.0 for w in result["windows"])
