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
async def test_market_data_ingestion_job(monkeypatch) -> None:
    async def fake_ingestion(_factory, **kwargs):
        symbols = kwargs["symbols"]
        return {"symbols_requested": len(symbols), "symbols_ok": len(symbols), "symbols_failed": 0, "inserted_total": 0, "errors": []}

    import titan_x.services.market_data_service as market_data_service
    monkeypatch.setattr(market_data_service, "run_market_data_ingestion", fake_ingestion)

    job = MarketDataIngestionJob(session_factory=object())
    result = await job._run({"symbols": ["AAPL", "GOOGL"]})
    assert result["symbols_ingested"] == 2
    assert result["symbols"] == ["AAPL", "GOOGL"]


@pytest.mark.asyncio
async def test_market_data_ingestion_default_symbols(monkeypatch) -> None:
    async def fake_ingestion(_factory, **kwargs):
        symbols = kwargs["symbols"]
        return {"symbols_requested": len(symbols), "symbols_ok": len(symbols), "symbols_failed": 0, "inserted_total": 0, "errors": []}

    import titan_x.services.market_data_service as market_data_service
    monkeypatch.setattr(market_data_service, "run_market_data_ingestion", fake_ingestion)

    job = MarketDataIngestionJob(session_factory=object())
    result = await job._run({})
    assert result["symbols_ingested"] == 3
    assert result["symbols"] == ["RELIANCE", "TCS", "HDFCBANK"]


@pytest.mark.asyncio
async def test_process_delayed_trades_job() -> None:
    job = ProcessDelayedTradesJob()
    result = await job._run({"batch_size": 50})
    assert result["batch_size"] == 50
