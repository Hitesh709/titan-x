import pytest

from titan_x.services.parameter_optimizer import ParameterOptimizer


def test_grid_search_ranks_best_parameters() -> None:
    optimizer = ParameterOptimizer()
    result = optimizer.grid_search(
        {"fast": [5, 10], "slow": [20, 30]},
        lambda p: 100.0 - p["fast"] - p["slow"],
        top_n=2,
    )
    assert result["evaluated"] == 4
    assert result["best"]["parameters"] == {"fast": 5, "slow": 20}
    assert result["best"]["rank"] == 1
    assert len(result["top_results"]) == 2


def test_random_search_is_reproducible() -> None:
    optimizer = ParameterOptimizer()
    space = {"fast": [5, 10, 15], "slow": [20, 30, 40]}
    score = lambda p: float(p["slow"] - p["fast"])
    a = optimizer.random_search(space, score, iterations=5, seed=7)
    b = optimizer.random_search(space, score, iterations=5, seed=7)
    assert a == b


def test_minimization_objective() -> None:
    optimizer = ParameterOptimizer()
    result = optimizer.grid_search({"x": [1, 2, 3]}, lambda p: float(p["x"]), maximize=False)
    assert result["best"]["parameters"] == {"x": 3}


def test_rejects_empty_space_and_invalid_top_n() -> None:
    optimizer = ParameterOptimizer()
    with pytest.raises(ValueError):
        optimizer.grid_search({}, lambda _: 1.0)
    with pytest.raises(ValueError):
        optimizer.grid_search({"x": [1]}, lambda _: 1.0, top_n=0)
