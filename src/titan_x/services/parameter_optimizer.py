from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import product
from random import Random
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class OptimizationResult:
    parameters: dict[str, Any]
    score: float
    rank: int


class ParameterOptimizer:
    """Deterministic grid/random parameter optimizer.

    The supplied evaluator must return a numeric objective score. Higher is
    better by default; set maximize=False for objectives such as drawdown.
    The optimizer itself is strategy-agnostic and therefore reusable by
    backtests, walk-forward evaluation, and future portfolio optimization.
    """

    def _validate_space(self, space: Mapping[str, Sequence[Any]]) -> None:
        if not space:
            raise ValueError("parameter space cannot be empty")
        for name, values in space.items():
            if not name or not values:
                raise ValueError(f"parameter '{name}' must have at least one value")

    def grid_search(
        self,
        parameter_space: Mapping[str, Sequence[Any]],
        evaluator: Callable[[dict[str, Any]], float],
        *,
        maximize: bool = True,
        top_n: int = 10,
    ) -> dict[str, Any]:
        self._validate_space(parameter_space)
        if top_n <= 0:
            raise ValueError("top_n must be positive")

        names = list(parameter_space)
        combinations = [dict(zip(names, values)) for values in product(*(parameter_space[n] for n in names))]
        results = [OptimizationResult(p, float(evaluator(p)), 0) for p in combinations]
        results.sort(key=lambda r: r.score, reverse=maximize)
        ranked = [OptimizationResult(r.parameters, r.score, i + 1) for i, r in enumerate(results)]
        return self._response("grid", ranked, len(combinations), top_n)

    def random_search(
        self,
        parameter_space: Mapping[str, Sequence[Any]],
        evaluator: Callable[[dict[str, Any]], float],
        *,
        iterations: int = 50,
        maximize: bool = True,
        top_n: int = 10,
        seed: int = 42,
    ) -> dict[str, Any]:
        self._validate_space(parameter_space)
        if iterations <= 0 or top_n <= 0:
            raise ValueError("iterations and top_n must be positive")

        rng = Random(seed)
        names = list(parameter_space)
        results: list[OptimizationResult] = []
        seen: set[tuple[Any, ...]] = set()
        max_unique = 1
        for values in parameter_space.values():
            max_unique *= len(values)
        target = min(iterations, max_unique)
        while len(results) < target:
            values = tuple(rng.choice(parameter_space[n]) for n in names)
            if values in seen:
                continue
            seen.add(values)
            params = dict(zip(names, values))
            results.append(OptimizationResult(params, float(evaluator(params)), 0))
        results.sort(key=lambda r: r.score, reverse=maximize)
        ranked = [OptimizationResult(r.parameters, r.score, i + 1) for i, r in enumerate(results)]
        return self._response("random", ranked, len(results), top_n, seed=seed)

    @staticmethod
    def _response(method: str, results: list[OptimizationResult], evaluated: int, top_n: int, **extra: Any) -> dict[str, Any]:
        return {
            "method": method,
            "evaluated": evaluated,
            "best": asdict(results[0]) if results else None,
            "top_results": [asdict(r) for r in results[:top_n]],
            **extra,
        }
