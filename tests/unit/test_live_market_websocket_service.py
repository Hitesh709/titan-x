import asyncio

import pytest

from titan_x.services.live_market_websocket_service import LiveMarketWebSocketService


@pytest.mark.asyncio
async def test_broadcasts_only_subscribed_quotes() -> None:
    messages: list[dict] = []

    async def poll(symbols: list[str]) -> dict:
        assert symbols == ["NSE:RELIANCE", "NSE:TCS"]
        return {
            "NSE:RELIANCE": {"price": 100},
            "NSE:TCS": {"price": 200},
            "NSE:INFY": {"price": 300},
        }

    async def send(message: dict) -> None:
        messages.append(message)

    service = LiveMarketWebSocketService(poll)
    connection_id = await service.connect(send, ["nse:reliance", "NSE:TCS", "NSE:TCS"])
    assert await service.broadcast_once() == 1
    assert messages[0]["type"] == "market.quote"
    assert set(messages[0]["quotes"]) == {"NSE:RELIANCE", "NSE:TCS"}
    await service.disconnect(connection_id)
    assert (await service.snapshot())["connections"] == 0


@pytest.mark.asyncio
async def test_failed_sender_is_removed() -> None:
    async def poll(symbols: list[str]) -> dict:
        return {symbol: {"price": 1} for symbol in symbols}

    async def send(_: dict) -> None:
        raise RuntimeError("socket closed")

    service = LiveMarketWebSocketService(poll)
    await service.connect(send, ["NSE:RELIANCE"])
    assert await service.broadcast_once() == 0
    assert (await service.snapshot())["connections"] == 0


@pytest.mark.asyncio
async def test_subscription_limit_is_enforced() -> None:
    service = LiveMarketWebSocketService(lambda _: asyncio.sleep(0, result={}))
    with pytest.raises(ValueError):
        await service.connect(lambda _: asyncio.sleep(0), [f"S{i}" for i in range(101)])
