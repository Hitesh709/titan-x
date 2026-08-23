import pytest

from titan_x.services.position_exposure_service import PositionExposureService


def test_long_position_and_unrealized_pnl() -> None:
    service = PositionExposureService(max_gross_exposure=100_000, max_symbol_exposure=50_000)
    position = service.apply_fill(symbol="RELIANCE", quantity=10, price=1000)
    assert position.quantity == 10
    position = service.mark_price("RELIANCE", 1100)
    assert position.market_value == 11_000
    assert position.unrealized_pnl == 1_000


def test_exposure_limits_are_enforced() -> None:
    service = PositionExposureService(max_gross_exposure=10_000, max_symbol_exposure=5_000)
    with pytest.raises(ValueError, match="symbol exposure"):
        service.apply_fill(symbol="TCS", quantity=6, price=1000)


def test_multiple_positions_report_gross_and_net() -> None:
    service = PositionExposureService(max_gross_exposure=100_000, max_symbol_exposure=50_000)
    service.apply_fill(symbol="A", quantity=10, price=100)
    service.apply_fill(symbol="B", quantity=-5, price=200)
    assert service.gross_exposure() == 2_000
    assert service.net_exposure() == 0
