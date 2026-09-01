from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from titan_x.services.point_in_time_prediction_engine import PointInTimePredictionEngine


def _engine() -> PointInTimePredictionEngine:
    engine = PointInTimePredictionEngine.__new__(PointInTimePredictionEngine)
    engine._prediction_as_of_date = date(2026, 1, 15)
    engine._session = MagicMock()
    return engine


@pytest.mark.parametrize(
    "method, expected_column",
    [
        ("_get_latest_price", "daily_prices.trade_date"),
        ("_get_similarities", "similarity_analyses.query_end_date"),
        ("_get_fundamentals", "fundamental_metrics.published_at"),
    ],
)
@pytest.mark.asyncio
async def test_point_in_time_queries_apply_cutoff(method: str, expected_column: str) -> None:
    engine = _engine()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    engine._session.execute = AsyncMock(return_value=result)

    await getattr(engine, method)("ABC")

    statement = engine._session.execute.await_args.args[0]
    sql = str(statement)
    assert expected_column in sql
    assert "2026-01-15" in sql


def test_as_of_datetime_is_end_of_day_utc() -> None:
    engine = _engine()
    value = engine._as_of_datetime(date(2026, 1, 15))
    assert value.isoformat() == "2026-01-15T23:59:59.999999+00:00"


def test_cutoff_explicit_date_overrides_context() -> None:
    engine = _engine()
    assert engine._cutoff(date(2026, 2, 1)) == date(2026, 2, 1)
    assert engine._cutoff(None) == date(2026, 1, 15)
