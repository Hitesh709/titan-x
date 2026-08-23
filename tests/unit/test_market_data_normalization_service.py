from datetime import datetime, timezone

import pytest

from titan_x.services.market_data_normalization_service import MarketDataNormalizationService


def test_normalizes_provider_aliases_and_types() -> None:
    service = MarketDataNormalizationService()
    result = service.normalize(
        " nse:reliance ",
        {
            "ltp": "2501.50",
            "change": "12.5",
            "change_percent": "0.5",
            "volume": "1000",
            "exchange": "nse",
            "currency": "inr",
            "timestamp": datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
        },
    )
    assert result["symbol"] == "NSE:RELIANCE"
    assert result["last_price"] == 2501.5
    assert result["exchange"] == "NSE"
    assert result["currency"] == "INR"


def test_rejects_non_finite_or_non_positive_price() -> None:
    service = MarketDataNormalizationService()
    with pytest.raises(ValueError, match="positive"):
        service.normalize("TCS", {"price": 0})
    with pytest.raises(ValueError, match="finite"):
        service.normalize("TCS", {"price": float("nan")})


def test_rejects_invalid_timestamp_and_negative_volume() -> None:
    service = MarketDataNormalizationService()
    with pytest.raises(ValueError, match="ISO-8601"):
        service.normalize("TCS", {"price": 100, "timestamp": "not-a-date"})
    with pytest.raises(ValueError, match="volume"):
        service.normalize("TCS", {"price": 100, "volume": -1})


def test_validate_checks_canonical_quote() -> None:
    service = MarketDataNormalizationService()
    service.validate({"symbol": "TCS", "last_price": 100, "timestamp": "2026-08-23T10:00:00+00:00"})
