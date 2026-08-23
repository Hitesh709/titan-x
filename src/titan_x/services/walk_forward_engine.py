from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    train_count: int
    test_count: int
    train_return_pct: float | None = None
    test_return_pct: float | None = None


class WalkForwardEngine:
    """Rolling train/test splitter with optional train/test evaluators.

    The engine deliberately does not optimize parameters itself. It prevents
    look-ahead leakage by ensuring every test window occurs strictly after its
    corresponding training window.
    """

    def generate_windows(
        self,
        dates: Sequence[date],
        train_size: int,
        test_size: int,
        step_size: int | None = None,
    ) -> list[WalkForwardWindow]:
        if train_size <= 0 or test_size <= 0:
            raise ValueError("train_size and test_size must be positive")
        step = test_size if step_size is None else step_size
        if step <= 0:
            raise ValueError("step_size must be positive")
        if any(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)):
            raise ValueError("dates must be strictly increasing")

        windows: list[WalkForwardWindow] = []
        start = 0
        while start + train_size + test_size <= len(dates):
            train_end = start + train_size
            test_end = train_end + test_size
            windows.append(
                WalkForwardWindow(
                    train_start=dates[start],
                    train_end=dates[train_end - 1],
                    test_start=dates[train_end],
                    test_end=dates[test_end - 1],
                    train_count=train_size,
                    test_count=test_size,
                )
            )
            start += step
        return windows

    def run(
        self,
        records: Sequence[dict[str, Any]],
        train_size: int,
        test_size: int,
        step_size: int | None = None,
        train_evaluator: Callable[[Sequence[dict[str, Any]]], float] | None = None,
        test_evaluator: Callable[[Sequence[dict[str, Any]]], float] | None = None,
    ) -> dict[str, Any]:
        dates = [r["date"] for r in records]
        windows = self.generate_windows(dates, train_size, test_size, step_size)
        results: list[dict[str, Any]] = []
        for w in windows:
            train = records[dates.index(w.train_start) : dates.index(w.train_end) + 1]
            test = records[dates.index(w.test_start) : dates.index(w.test_end) + 1]
            item = asdict(w)
            item["train_return_pct"] = train_evaluator(train) if train_evaluator else None
            item["test_return_pct"] = test_evaluator(test) if test_evaluator else None
            results.append(item)
        return {
            "windows": results,
            "window_count": len(results),
            "out_of_sample_count": sum(w["test_count"] for w in results),
        }
