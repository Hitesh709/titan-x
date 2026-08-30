from datetime import datetime, timezone

import pytest

from titan_x.services.market_data_gateway_service import MarketDataGateway


@pytest.mark.asyncio
async def test_gateway_accepts_valid_quote_and_builds_candle() -> None:
    async def fetch(symbol: str) -> dict:
        return {
            "symbol": symbol,
            "last_price": 250.5,
            "volume": 1000,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exchange": "NSE",
        }

    gateway = MarketDataGateway(fetch, provider_name="test")
    quote = await gateway.ingest("RELIANCE")

    assert quote["last_price"] == 250.5
    assert quote["status"] == "valid"
    assert gateway.get_candles("RELIANCE", 1, 10)[0]["close"] == 250.5
    assert gateway.health(["RELIANCE"])["tradeable"] is True


@pytest.mark.asyncio
async def test_gateway_rejects_out_of_order_tick() -> None:
    timestamps = [
        "2026-08-30T10:00:02+00:00",
        "2026-08-30T10:00:01+00:00",
    ]

    async def fetch(symbol: str) -> dict:
        return {"symbol": symbol, "last_price": 100, "timestamp": timestamps.pop(0)}

    gateway = MarketDataGateway(fetch, provider_name="test")
    await gateway.ingest("TCS")
    with pytest.raises(ValueError, match="out-of-order"):
        await gateway.ingest("TCS")


@pytest.mark.asyncio
async def test_stale_quote_is_not_tradeable() -> None:
    async def fetch(symbol: str) -> dict:
        return {
            "symbol": symbol,
            "last_price": 100,
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    gateway = MarketDataGateway(fetch, provider_name="test", stale_after_seconds=15)
    with pytest.raises(ValueError, match="stale"):
        await gateway.quote("INFY")
