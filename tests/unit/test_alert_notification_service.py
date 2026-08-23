import pytest

from titan_x.services.alert_notification_service import AlertNotificationService


@pytest.mark.asyncio
async def test_emits_alert_and_dispatches_handler() -> None:
    received = []
    service = AlertNotificationService()
    service.add_handler(received.append)
    alert = await service.emit(severity="CRITICAL", event_type="RISK", message="Daily loss limit reached", symbol="TCS")
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert received[0] == alert


@pytest.mark.asyncio
async def test_duplicate_alert_is_suppressed() -> None:
    service = AlertNotificationService(dedupe_seconds=60)
    first = await service.emit(severity="WARNING", event_type="STALE_DATA", message="Quote is stale", symbol="TCS")
    second = await service.emit(severity="WARNING", event_type="STALE_DATA", message="Quote is stale", symbol="TCS")
    assert first is not None
    assert second is None
    assert len(service.history()) == 1


def test_invalid_alert_rejected() -> None:
    service = AlertNotificationService()
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(service.emit(severity="URGENT", event_type="RISK", message="x"))
