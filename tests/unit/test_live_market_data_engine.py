import asyncio

import pytest

from titan_x.services.live_market_data_engine import LiveMarketDataEngine


@pytest.mark.asyncio
async def test_poll_normalizes_quotes_and_increments_sequence() -> None:
    async def fetch(symbol: str) -> dict:
        return {"ltp": 100.5, "change": 1.5, "change_percent": 1.52, "source": "test"}

    engine = LiveMarketDataEngine(fetch)
    result = await engine.poll_once(["nse:test", "NSE:TEST"])

    assert result["updated"] == 1
    quote = engine.get_latest("NSE:TEST")
    assert quote is not None
    assert quote.last_price == 100.5
    assert quote.sequence == 1

    await engine.poll_once(["NSE:TEST"])
    assert engine.get_latest("NSE:TEST").sequence == 2


@pytest.mark.asyncio
async def test_bad_provider_does_not_stop_other_symbols() -> None:
    async def fetch(symbol: str) -> dict:
        if symbol == "BAD":
            raise RuntimeError("provider unavailable")
        return {"price": 250}

    engine = LiveMarketDataEngine(fetch)
    result = await engine.poll_once(["GOOD", "BAD"])
    assert result["updated"] == 1
    assert result["failed"] == 1
    assert result["errors"][0]["symbol"] == "BAD"


@pytest.mark.asyncio
async def test_subscriber_failure_isolated() -> None:
    received = []

    async def fetch(symbol: str) -> dict:
        return {"price": 10}

    async def failing(_quote) -> None:
        raise RuntimeError("consumer failure")

    def healthy(quote) -> None:
        received.append(quote.symbol)

    engine = LiveMarketDataEngine(fetch)
    engine.subscribe(failing)
    engine.subscribe(healthy)
    await engine.poll_once(["ABC"])
    assert received == ["ABC"]


@pytest.mark.asyncio
async def test_background_run_can_be_stopped() -> None:
    async def fetch(_symbol: str) -> dict:
        return {"price": 10}

    engine = LiveMarketDataEngine(fetch)
    task = asyncio.create_task(engine.run(["ABC"], interval_seconds=60))
    await asyncio.sleep(0)
    engine.stop()
    await asyncio.wait_for(task, timeout=1)


def test_invalid_payloads_are_rejected() -> None:
    with pytest.raises(ValueError):
        LiveMarketDataEngine.normalize("ABC", {}, 1)
    with pytest.raises(ValueError):
        LiveMarketDataEngine.normalize("ABC", {"price": 0}, 1)
