from datetime import date

import pytest

from titan_x.services.benchmark_analyzer import BenchmarkAnalyzer


def test_benchmark_comparison_calculates_alpha():
    analyzer = BenchmarkAnalyzer()
    result = analyzer.compare(
        [
            {"equity": 1000.0},
            {"equity": 1200.0},
        ],
        [date(2026, 1, 1), date(2026, 1, 2)],
        [100.0, 110.0],
        1000.0,
    )

    assert result["strategy_return_pct"] == pytest.approx(20.0)
    assert result["benchmark_return_pct"] == pytest.approx(10.0)
    assert result["alpha_pct"] == pytest.approx(10.0)


def test_benchmark_comparison_rejects_mismatched_series():
    with pytest.raises(ValueError, match="same length"):
        BenchmarkAnalyzer().compare(
            [{"equity": 1000.0}],
            [date(2026, 1, 1), date(2026, 1, 2)],
            [100.0],
            1000.0,
        )


def test_benchmark_comparison_handles_empty_data():
    result = BenchmarkAnalyzer().compare([], [], [], 1000.0)
    assert result["alpha_pct"] == 0.0
