from __future__ import annotations

import asyncio
import secrets
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.services.live_market_data_engine import LiveMarketDataEngine
from titan_x.services.live_market_websocket_service import LiveMarketWebSocketService

router = APIRouter(prefix="/live-market", tags=["live-market"])


def _service() -> LiveMarketWebSocketService:
    settings = get_settings()
    provider_name = settings.market_data_provider
    provider = get_market_data_provider(provider_name)

    async def poll(symbols: list[str]) -> dict:
        engine = LiveMarketDataEngine(
            lambda symbol: provider.get_quote(symbol, synthetic_ok=provider_name.lower() == "mock")
        )
        return await engine.poll_once(symbols)

    return LiveMarketWebSocketService(poll, interval=1.0)


@router.websocket("/ws")
async def live_market_websocket(
    websocket: WebSocket,
    symbols: Annotated[str, Query(description="Comma-separated symbols, maximum 100")],
    api_key: Annotated[str | None, Query(description="API key for browser WebSocket clients")] = None,
) -> None:
    settings = get_settings()
    expected = settings.api_key.get_secret_value()
    if api_key is None or not secrets.compare_digest(api_key, expected):
        await websocket.close(code=1008, reason="Invalid API key")
        return

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms or len(syms) > 100:
        await websocket.close(code=1008, reason="Provide 1-100 symbols")
        return

    await websocket.accept()
    service = _service()
    stop_event = asyncio.Event()
    connection_id = await service.connect(websocket.send_json, syms)
    task = asyncio.create_task(service.run(stop_event))
    try:
        await websocket.send_json({"type": "market.connected", "symbols": syms})
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        stop_event.set()
        await service.disconnect(connection_id)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await service.close()
