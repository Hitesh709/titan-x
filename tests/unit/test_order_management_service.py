import pytest

from titan_x.services.order_management_service import OrderManagementService


@pytest.mark.asyncio
async def test_simulation_order_is_accepted_and_tracked() -> None:
    service = OrderManagementService(mode="SIMULATION")
    order = await service.submit(symbol="NSE:RELIANCE", side="BUY", quantity=10, strategy="trend")
    assert order.status == "ACCEPTED"
    assert service.get(order.order_id) == order
    assert len(service.list_open()) == 1


def test_cancel_order() -> None:
    service = OrderManagementService()
    import asyncio
    order = asyncio.run(service.submit(symbol="TCS", side="SELL", quantity=5))
    cancelled = service.cancel(order.order_id)
    assert cancelled.status == "CANCELLED"
    assert service.list_open() == []


@pytest.mark.asyncio
async def test_validation_and_limit_price() -> None:
    service = OrderManagementService(max_quantity=10)
    with pytest.raises(ValueError):
        await service.submit(symbol="TCS", side="HOLD", quantity=1)
    with pytest.raises(ValueError):
        await service.submit(symbol="TCS", side="BUY", quantity=11)
    with pytest.raises(ValueError):
        await service.submit(symbol="TCS", side="BUY", quantity=1, order_type="LIMIT")
