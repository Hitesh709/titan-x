import pytest
from httpx import AsyncClient


class TestIntradayAPI:
    @pytest.mark.asyncio
    async def test_create_bar(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "AAPL",
            "timestamp": "2024-01-02T10:00:00Z",
            "resolution": "1min",
            "open": 180.0,
            "high": 185.0,
            "low": 179.0,
            "close": 184.0,
            "volume": 1000,
        }
        resp = await client.post("/api/v1/intraday", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["resolution"] == "1min"

    @pytest.mark.asyncio
    async def test_create_bar_invalid_resolution(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "AAPL",
            "timestamp": "2024-01-02T10:00:00Z",
            "resolution": "bad",
            "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000,
        }
        resp = await client.post("/api/v1/intraday", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_bar_duplicate(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "AAPL",
            "timestamp": "2024-01-02T10:00:00Z",
            "resolution": "1min",
            "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000,
        }
        r1 = await client.post("/api/v1/intraday", json=payload)
        assert r1.status_code == 201
        r2 = await client.post("/api/v1/intraday", json=payload)
        assert r2.status_code == 409

    @pytest.mark.asyncio
    async def test_list_bars(self, client: AsyncClient) -> None:
        await client.post("/api/v1/intraday", json={"symbol": "AAPL", "timestamp": "2024-01-02T10:00:00Z", "resolution": "1min", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000})
        await client.post("/api/v1/intraday", json={"symbol": "AAPL", "timestamp": "2024-01-02T10:01:00Z", "resolution": "1min", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200})
        resp = await client.get("/api/v1/intraday/AAPL/1min")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_list_bars_date_range(self, client: AsyncClient) -> None:
        await client.post("/api/v1/intraday", json={"symbol": "AAPL", "timestamp": "2024-01-02T10:00:00Z", "resolution": "1min", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000})
        await client.post("/api/v1/intraday", json={"symbol": "AAPL", "timestamp": "2024-01-02T11:00:00Z", "resolution": "1min", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200})
        resp = await client.get("/api/v1/intraday/AAPL/1min?start=2024-01-02T10:30:00Z")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_bulk_import(self, client: AsyncClient) -> None:
        records = [
            {"timestamp": "2024-01-02T10:00:00Z", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000},
            {"timestamp": "2024-01-02T10:01:00Z", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200},
        ]
        resp = await client.post("/api/v1/intraday/bulk/AAPL/1min", json=records)
        assert resp.status_code == 200
        assert resp.json()["created"] == 2

    @pytest.mark.asyncio
    async def test_aggregate_resolution(self, client: AsyncClient) -> None:
        base = "2024-01-02T10:0{}:00Z"
        for i in range(5):
            await client.post("/api/v1/intraday", json={"symbol": "AAPL", "timestamp": base.format(i), "resolution": "1min", "open": 180 + i, "high": 185 + i, "low": 179 + i, "close": 184 + i, "volume": 1000})
        resp = await client.post("/api/v1/intraday/aggregate/AAPL?source=1min&target=5min")
        assert resp.status_code == 200
        assert resp.json()["bars_created"] == 1

    @pytest.mark.asyncio
    async def test_aggregate_to_daily(self, client: AsyncClient) -> None:
        for i in range(3):
            await client.post("/api/v1/intraday", json={"symbol": "AAPL", "timestamp": f"2024-01-02T1{i}:00:00Z", "resolution": "hourly", "open": 180 + i, "high": 185 + i, "low": 179 + i, "close": 184 + i, "volume": 1000})
        resp = await client.post("/api/v1/intraday/aggregate/AAPL/daily")
        assert resp.status_code == 200
        assert resp.json()["bars_created"] == 1

    @pytest.mark.asyncio
    async def test_delete_bars(self, client: AsyncClient) -> None:
        await client.post("/api/v1/intraday", json={"symbol": "AAPL", "timestamp": "2024-01-02T10:00:00Z", "resolution": "1min", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000})
        resp = await client.delete("/api/v1/intraday/AAPL")
        assert resp.status_code == 200
        assert "Deleted" in resp.json()["message"]
