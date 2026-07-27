import pytest

from titan_x.jobs.market_jobs import (
    MarketCloseJob,
    MarketDataIngestionJob,
    MarketOpenJob,
    ProcessDelayedTradesJob,
)


@pytest.mark.asyncio
async def test_market_open_job() -> None:
    job = MarketOpenJob()
    result = await job._run({})
    assert result["market"] == "open"


@pytest.mark.asyncio
async def test_market_close_job() -> None:
    job = MarketCloseJob()
    result = await job._run({})
    assert result["market"] == "closed"


@pytest.mark.asyncio
async def test_market_data_ingestion_job() -> None:
    job = MarketDataIngestionJob()
    result = await job._run({"symbols": ["AAPL", "GOOGL"]})
    assert result["symbols_ingested"] == 2
    assert result["symbols"] == ["AAPL", "GOOGL"]


@pytest.mark.asyncio
async def test_market_data_ingestion_default_symbols() -> None:
    job = MarketDataIngestionJob()
    result = await job._run({})
    assert result["symbols_ingested"] == 3


@pytest.mark.asyncio
async def test_process_delayed_trades_job() -> None:
    job = ProcessDelayedTradesJob()
    result = await job._run({"batch_size": 50})
    assert result["batch_size"] == 50
