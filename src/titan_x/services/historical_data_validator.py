from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any


class HistoricalDataValidationError(ValueError):
    """Raised when historical OHLCV data is unsafe for backtesting."""


class HistoricalDataValidator:
    """Validate chronological OHLCV data before it reaches the backtest engine."""

    @staticmethod
    def validate(
        prices: list[dict[str, Any]],
        symbol: str,
        start: date,
        end: date,
        minimum_bars: int = 30,
    ) -> None:
        if start > end:
            raise HistoricalDataValidationError("start_date must be on or before end_date")
        if not prices:
            raise HistoricalDataValidationError(
                f"No historical price data for {symbol}: Insufficient price data; no data available between {start} and {end}"
            )

        previous_date: date | None = None
        for index, row in enumerate(prices):
            row_date = row.get("date")
            if row_date is None:
                raise HistoricalDataValidationError(f"Missing trade date at row {index}")
            if previous_date is not None and row_date <= previous_date:
                raise HistoricalDataValidationError(
                    f"Historical data for {symbol} is not strictly chronological at {row_date}"
                )
            previous_date = row_date

            try:
                open_price = float(row["open"])
                high = float(row["high"])
                low = float(row["low"])
                close = float(row["close"])
                volume = float(row["volume"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HistoricalDataValidationError(
                    f"Invalid OHLCV values for {symbol} on {row_date}"
                ) from exc

            values = (open_price, high, low, close, volume)
            if not all(isfinite(value) for value in values):
                raise HistoricalDataValidationError(
                    f"Non-finite OHLCV value for {symbol} on {row_date}"
                )
            if min(open_price, high, low, close) <= 0:
                raise HistoricalDataValidationError(
                    f"Non-positive price for {symbol} on {row_date}"
                )
            if volume < 0:
                raise HistoricalDataValidationError(
                    f"Negative volume for {symbol} on {row_date}"
                )
            if high < max(open_price, close) or low > min(open_price, close) or high < low:
                raise HistoricalDataValidationError(
                    f"Invalid OHLC relationship for {symbol} on {row_date}"
                )

        if len(prices) < minimum_bars:
            raise HistoricalDataValidationError(
                f"Insufficient price data for {symbol}: {len(prices)} bars (minimum {minimum_bars})"
            )
