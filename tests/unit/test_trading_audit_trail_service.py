from titan_x.services.trading_audit_trail_service import TradingAuditTrailService


def test_audit_events_are_hash_chained_and_verifiable() -> None:
    service = TradingAuditTrailService()
    first = service.record(event_type="SIGNAL", actor="strategy", symbol="TCS", payload={"action": "BUY"})
    second = service.record(event_type="ORDER_ACCEPTED", actor="risk", symbol="TCS", payload={"quantity": 10})
    assert second.previous_hash == first.event_hash
    assert service.verify() is True
    assert len(service.list_events()) == 2


def test_tampering_is_detected() -> None:
    service = TradingAuditTrailService()
    service.record(event_type="ORDER", actor="system", payload={"status": "ACCEPTED"})
    service._events[0].payload["status"] = "FILLED"
    assert service.verify() is False
