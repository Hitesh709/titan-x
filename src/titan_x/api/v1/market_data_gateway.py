from __future__ import annotations

import asyncio
import contextlib
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from titan_x.api.dependencies import get_current_active_user
from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.user import User
from titan_x.services.market_data_gateway_service import MarketDataGateway

router = APIRouter(prefix="/market-data-gateway", tags=["market-data-gateway"])


def _gateway() -> MarketDataGateway:
    settings = get_settings()
    provider_name = settings.market_data_provider
    provider = get_market_data_provider(provider_name)
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)

    async def fetch(symbol: str) -> dict:
        try:
            return await provider.get_quote(symbol, synthetic_ok=False)
        except TypeError:
            return await provider.get_quote(symbol)

    return MarketDataGateway(fetch, provider_name=provider_name, redis=redis, stale_after_seconds=15.0)


@router.get("/quote/{symbol}")
async def quote(
    symbol: str,
    refresh: bool = Query(True),
    _: User = Depends(get_current_active_user),
):
    gateway = _gateway()
    try:
        return await gateway.quote(symbol, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await gateway.close()


@router.get("/candles/{symbol}")
async def candles(
    symbol: str,
    interval: int = Query(1, alias="interval_minutes", ge=1, le=60),
    limit: int = Query(100, ge=1, le=1000),
    _: User = Depends(get_current_active_user),
):
    gateway = _gateway()
    try:
        # A candle cache is intentionally built only from validated live ticks.
        await gateway.ingest(symbol)
        return {
            "symbol": symbol.upper(),
            "interval_minutes": interval,
            "source": gateway.provider_name,
            "candles": gateway.get_candles(symbol, interval, limit),
        }
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await gateway.close()


@router.get("/health")
async def health(
    symbols: str = Query(..., description="Comma-separated symbols"),
    _: User = Depends(get_current_active_user),
):
    gateway = _gateway()
    try:
        names = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not names or len(names) > 100:
            raise HTTPException(status_code=400, detail="Provide 1-100 symbols")
        results = await asyncio.gather(*(gateway.ingest(s) for s in names), return_exceptions=True)
        errors = [{"symbol": s, "error": str(r)} for s, r in zip(names, results) if isinstance(r, Exception)]
        state = gateway.health(names)
        state["errors"] = errors
        state["tradeable"] = not errors and state["tradeable"]
        return state
    finally:
        await gateway.close()


@router.websocket("/ws")
async def stream(
    websocket: WebSocket,
    symbols: Annotated[str, Query(description="Comma-separated symbols, maximum 100")],
    api_key: Annotated[str | None, Query()] = None,
) -> None:
    settings = get_settings()
    expected = settings.api_key.get_secret_value()
    if api_key is None or not secrets.compare_digest(api_key, expected):
        await websocket.close(code=1008, reason="Invalid API key")
        return
    names = list(dict.fromkeys(s.strip().upper() for s in symbols.split(",") if s.strip()))
    if not names or len(names) > 100:
        await websocket.close(code=1008, reason="Provide 1-100 symbols")
        return

    await websocket.accept()
    gateway = _gateway()
    stop = asyncio.Event()

    async def producer() -> None:
        while not stop.is_set():
            for symbol in names:
                try:
                    quote = await gateway.ingest(symbol)
                    await websocket.send_json({"type": "market.tick", "data": quote})
                except Exception as exc:
                    await websocket.send_json({"type": "market.error", "symbol": symbol, "error": str(exc)})
            try:
                await asyncio.wait_for(stop.wait(), 1.0)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(producer())
    try:
        await websocket.send_json({"type": "market.connected", "provider": gateway.provider_name, "symbols": names})
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await gateway.close()
