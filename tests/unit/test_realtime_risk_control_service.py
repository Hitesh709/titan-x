from titan_x.services.realtime_risk_control_service import RealtimeRiskControlService


def test_approves_valid_order() -> None:
    service = RealtimeRiskControlService(max_order_value=20_000, max_gross_exposure=100_000)
    decision = service.approve(symbol="RELIANCE", action="BUY", quantity=10, price=1000, current_gross_exposure=10_000)
    assert decision.approved is True
    assert decision.projected_exposure == 20_000


def test_blocks_order_value_and_daily_loss() -> None:
    service = RealtimeRiskControlService(max_order_value=5_000, max_daily_loss=1_000)
    assert service.approve(symbol="TCS", action="BUY", quantity=10, price=1000, current_gross_exposure=0).approved is False
    service.record_realized_pnl(-1_000)
    assert service.approve(symbol="TCS", action="BUY", quantity=1, price=100, current_gross_exposure=0).approved is False


def test_kill_switch_blocks_everything() -> None:
    service = RealtimeRiskControlService()
    service.set_kill_switch(True)
    decision = service.approve(symbol="TCS", action="BUY", quantity=1, price=100, current_gross_exposure=0)
    assert decision.approved is False
    assert "kill switch" in decision.reason
