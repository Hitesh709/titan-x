"""Market data record validation."""
from datetime import date
from typing import Any

from titan_x.services.market_data_collection.models import ValidationOutcome


class DataValidator:
    VALIDATION_RULES = [
        "positive_price",
        "high_low_consistency",
        "open_close_range",
        "positive_volume",
        "no_nan_values",
        "no_infinite_values",
        "date_not_future",
        "ohlc_consistency",
    ]

    def validate(self, record: dict[str, Any]) -> ValidationOutcome:
        outcome = ValidationOutcome()
        errors: list[str] = []

        if self._check_positive_price(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("price_not_positive")

        if self._check_high_low_consistency(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("high_low_inconsistent")

        if self._check_open_close_range(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("open_close_out_of_range")

        if self._check_positive_volume(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("volume_not_positive")

        if self._check_no_nan(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("nan_value_found")

        if self._check_no_infinite(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("infinite_value_found")

        if self._check_date_not_future(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("date_in_future")

        if self._check_ohlc_consistency(record):
            outcome.checks_passed += 1
        else:
            outcome.checks_failed += 1
            errors.append("ohlc_consistency_failed")

        outcome.passed = outcome.checks_failed == 0
        outcome.errors = errors
        return outcome

    @staticmethod
    def _check_positive_price(record: dict[str, Any]) -> bool:
        return all(
            record.get(k, 0) is not None and record.get(k, 0) > 0
            for k in ("open", "high", "low", "close")
        )

    @staticmethod
    def _check_high_low_consistency(record: dict[str, Any]) -> bool:
        high = record.get("high")
        low = record.get("low")
        if high is None or low is None:
            return False
        return high >= low

    @staticmethod
    def _check_open_close_range(record: dict[str, Any]) -> bool:
        high = record.get("high")
        low = record.get("low")
        opn = record.get("open")
        close = record.get("close")
        if any(v is None for v in (high, low, opn, close)):
            return False
        return low <= opn <= high and low <= close <= high

    @staticmethod
    def _check_positive_volume(record: dict[str, Any]) -> bool:
        vol = record.get("volume")
        return vol is not None and vol > 0

    @staticmethod
    def _check_no_nan(record: dict[str, Any]) -> bool:
        import math
        for k in ("open", "high", "low", "close", "volume"):
            v = record.get(k)
            if v is not None and isinstance(v, float) and math.isnan(v):
                return False
        return True

    @staticmethod
    def _check_no_infinite(record: dict[str, Any]) -> bool:
        import math
        for k in ("open", "high", "low", "close", "volume"):
            v = record.get(k)
            if v is not None and isinstance(v, float) and math.isinf(v):
                return False
        return True

    @staticmethod
    def _check_date_not_future(record: dict[str, Any]) -> bool:
        d = record.get("trade_date")
        if d is None:
            return False
        if isinstance(d, str):
            d = date.fromisoformat(d)
        return d <= date.today()

    @staticmethod
    def _check_ohlc_consistency(record: dict[str, Any]) -> bool:
        close = record.get("close")
        opn = record.get("open")
        if close is None or opn is None:
            return False
        return abs(close - opn) <= abs(record.get("high", 0) - record.get("low", 0)) * 2