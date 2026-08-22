from datetime import date, timedelta

import pytest

from titan_x.services.historical_data_validator import (
    HistoricalDataValidationError,
    HistoricalDataValidator,
)


def _row(day: date, price: float = 100.0, volume: int = 1000) -> dict:
    return {
        "date": day,
        "open": price,
        "high": price + 1,
        "low": price - 1,
        "close": price,
        "volume": volume,
    }


def _valid_rows(count: int = 30) -> list[dict]:
    start = date(2025, 1, 1)
    return [_row(start + timedelta(days=i), 100 + i) for i in range(count)]


def test_valid_ohlcv_history_passes() -> None:
    rows = _valid_rows()
    HistoricalDataValidator.validate(rows, "RELIANCE", rows[0]["date"], rows[-1]["date"])


def test_empty_history_is_rejected() -> None:
    with pytest.raises(HistoricalDataValidationError, match="No historical price data"):
        HistoricalDataValidator.validate([], "RELIANCE", date(2025, 1, 1), date(2025, 1, 31))


def test_short_history_is_rejected() -> None:
    rows = _valid_rows(29)
    with pytest.raises(HistoricalDataValidationError, match="Insufficient price data"):
        HistoricalDataValidator.validate(rows, "RELIANCE", rows[0]["date"], rows[-1]["date"])


def test_non_chronological_history_is_rejected() -> None:
    rows = _valid_rows()
    rows[5]["date"] = rows[4]["date"]
    with pytest.raises(HistoricalDataValidationError, match="not strictly chronological"):
        HistoricalDataValidator.validate(rows, "RELIANCE", rows[0]["date"], rows[-1]["date"])


def test_invalid_ohlc_relationship_is_rejected() -> None:
    rows = _valid_rows()
    rows[10]["high"] = rows[10]["low"] - 1
    with pytest.raises(HistoricalDataValidationError, match="Invalid OHLC relationship"):
        HistoricalDataValidator.validate(rows, "RELIANCE", rows[0]["date"], rows[-1]["date"])


def test_negative_volume_is_rejected() -> None:
    rows = _valid_rows()
    rows[10]["volume"] = -1
    with pytest.raises(HistoricalDataValidationError, match="Negative volume"):
        HistoricalDataValidator.validate(rows, "RELIANCE", rows[0]["date"], rows[-1]["date"])
