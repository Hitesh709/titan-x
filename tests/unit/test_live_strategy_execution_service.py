import pytest

from titan_x.services.live_strategy_execution_service import LiveStrategyExecutionService


@pytest.mark.asyncio
async def test_approved_signal_creates_execution_decision() -> None:
    decisions = []
    service = LiveStrategyExecutionService(min_confidence=70)
    service.set_handler(decisions.append)
    decision = await service.execute({
        "symbol": "NSE:RELIANCE", "action": "BUY", "confidence": 90,
        "price": 1500, "strategy": "trend", "reason": "breakout"
    }, quantity=10)
    assert decision is not None
    assert decision.quantity == 10
    assert decision.action == "BUY"
    assert len(decisions) == 1


@pytest.mark.asyncio
async def test_low_confidence_and_hold_are_not_executed() -> None:
    service = LiveStrategyExecutionService(min_confidence=80)
    assert await service.execute({"symbol": "TCS", "action": "BUY", "confidence": 70, "price": 3000}) is None
    assert await service.execute({"symbol": "TCS", "action": "HOLD", "confidence": 99, "price": 3000}) is None


@pytest.mark.asyncio
async def test_quantity_limit_is_enforced() -> None:
    service = LiveStrategyExecutionService(max_quantity=10)
    with pytest.raises(ValueError, match="quantity"):
        await service.execute({"symbol": "TCS", "action": "BUY", "confidence": 90, "price": 3000}, quantity=11)
