import pytest

from titan_x.services.live_pnl_monitor_service import LivePnlMonitorService


def test_portfolio_snapshot_calculates_pnl_and_exposure() -> None:
    service = LivePnlMonitorService(starting_equity=100_000)
    snapshot = service.update(
        positions={
            "RELIANCE": {"quantity": 10, "average_price": 1000, "last_price": 1100},
            "TCS": {"quantity": -5, "average_price": 2000, "last_price": 1900},
        },
        realized_pnl=500,
    )
    assert snapshot.gross_exposure == 20_500
    assert snapshot.net_exposure == 1_500
    assert snapshot.unrealized_pnl == 1_500
    assert snapshot.total_pnl == 2_000
    assert snapshot.equity == 102_000
    assert snapshot.return_pct == 2


def test_invalid_position_price_is_rejected() -> None:
    service = LivePnlMonitorService(starting_equity=100_000)
    with pytest.raises(ValueError, match="price"):
        service.update(positions={"TCS": {"quantity": 1, "last_price": 0}})
