import pytest

from titan_x.services.live_signal_pipeline import LiveSignalPipeline


@pytest.mark.asyncio
async def test_emits_valid_signal_and_suppresses_duplicate() -> None:
    events = []

    def scorer(symbol, quote):
        return {"action": "BUY", "confidence": 90, "strategy": "trend", "reason": "uptrend"}

    pipeline = LiveSignalPipeline(scorer, min_confidence=70)
    pipeline.subscribe(events.append)

    first = await pipeline.process_quote({"symbol": "NSE:RELIANCE", "last_price": 1500})
    second = await pipeline.process_quote({"symbol": "NSE:RELIANCE", "last_price": 1510})

    assert first is not None
    assert first.action == "BUY"
    assert first.confidence == 90
    assert second is None
    assert len(events) == 1


@pytest.mark.asyncio
async def test_low_confidence_is_filtered() -> None:
    pipeline = LiveSignalPipeline(lambda *_: {"action": "SELL", "confidence": 50}, min_confidence=70)
    assert await pipeline.process_quote({"symbol": "TCS", "price": 3000}) is None


@pytest.mark.asyncio
async def test_invalid_action_rejected() -> None:
    pipeline = LiveSignalPipeline(lambda *_: {"action": "MAYBE", "confidence": 90})
    with pytest.raises(ValueError, match="invalid signal action"):
        await pipeline.process_quote({"symbol": "TCS", "price": 3000})
