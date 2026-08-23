import pytest

from titan_x.services.index_data_integrity_service import IndexDataIntegrityService


def test_nifty50_is_canonicalized() -> None:
    service = IndexDataIntegrityService()
    quote = service.normalize("NIFTY50", {"provider_symbol": "NIFTY 50", "exchange": "NSE", "last_price": 25000, "previous_close": 24900})
    assert quote["index"] == "NIFTY_50"
    assert quote["change"] == 100


def test_sensex_is_canonicalized() -> None:
    quote = IndexDataIntegrityService().normalize("BSE SENSEX", {"provider_symbol": "SENSEX", "exchange": "BSE", "last_price": 82000})
    assert quote["index"] == "SENSEX"
    assert quote["exchange"] == "BSE"


def test_cross_index_and_exchange_mismatch_are_rejected() -> None:
    service = IndexDataIntegrityService()
    with pytest.raises(ValueError, match="identity mismatch"):
        service.normalize("NIFTY50", {"provider_symbol": "SENSEX", "exchange": "NSE", "last_price": 82000})
    with pytest.raises(ValueError, match="exchange mismatch"):
        service.normalize("SENSEX", {"provider_symbol": "SENSEX", "exchange": "NSE", "last_price": 82000})


def test_ohlc_and_change_integrity_are_rejected() -> None:
    service = IndexDataIntegrityService()
    with pytest.raises(ValueError, match="high"):
        service.normalize("NIFTY50", {"provider_symbol": "NIFTY 50", "exchange": "NSE", "last_price": 100, "high": 90, "low": 80})
    with pytest.raises(ValueError, match="change"):
        service.normalize("NIFTY50", {"provider_symbol": "NIFTY 50", "exchange": "NSE", "last_price": 110, "previous_close": 100, "change": 1})
