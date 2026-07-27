import pytest
from httpx import AsyncClient


class TestPricesAPI:
    @pytest.mark.asyncio
    async def test_create_price(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "AAPL",
            "trade_date": "2024-01-02",
            "open": 180.0,
            "high": 185.0,
            "low": 179.0,
            "close": 184.0,
            "volume": 50000000,
        }
        resp = await client.post("/api/v1/prices", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["close"] == 184.0

    @pytest.mark.asyncio
    async def test_create_price_invalid_returns_409(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "AAPL",
            "trade_date": "2024-01-02",
            "open": 200, "high": 150, "low": 140, "close": 160, "volume": 1000,
        }
        resp = await client.post("/api/v1/prices", json=payload)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_prices(self, client: AsyncClient) -> None:
        await client.post("/api/v1/prices", json={"symbol": "AAPL", "trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000})
        await client.post("/api/v1/prices", json={"symbol": "AAPL", "trade_date": "2024-01-03", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200})
        resp = await client.get("/api/v1/prices/AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_prices_date_range(self, client: AsyncClient) -> None:
        await client.post("/api/v1/prices", json={"symbol": "AAPL", "trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000})
        await client.post("/api/v1/prices", json={"symbol": "AAPL", "trade_date": "2024-01-03", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200})
        resp = await client.get("/api/v1/prices/AAPL?start_date=2024-01-03")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_get_latest_price(self, client: AsyncClient) -> None:
        await client.post("/api/v1/prices", json={"symbol": "AAPL", "trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000})
        await client.post("/api/v1/prices", json={"symbol": "AAPL", "trade_date": "2024-01-03", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200})
        resp = await client.get("/api/v1/prices/AAPL/latest")
        assert resp.status_code == 200
        assert resp.json()["trade_date"] == "2024-01-03"

    @pytest.mark.asyncio
    async def test_get_latest_price_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/prices/UNKNOWN/latest")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_price(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/prices", json={"symbol": "AAPL", "trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000})
        price_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/prices/{price_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bulk_import(self, client: AsyncClient) -> None:
        payload = [
            {"trade_date": "2024-01-02", "open": 180, "high": 185, "low": 179, "close": 184, "volume": 1000},
            {"trade_date": "2024-01-03", "open": 184, "high": 190, "low": 183, "close": 188, "volume": 1200},
        ]
        resp = await client.post("/api/v1/prices/bulk/AAPL", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 2

    @pytest.mark.asyncio
    async def test_bulk_import_csv(self, client: AsyncClient) -> None:
        csv_content = "trade_date,open,high,low,close,volume\n2024-01-02,180,185,179,184,1000\n2024-01-03,184,190,183,188,1200\n"
        resp = await client.post("/api/v1/prices/bulk/AAPL/csv", json={"csv": csv_content})
        assert resp.status_code == 200
        assert resp.json()["created"] == 2


class TestCorporateActionsAPI:
    @pytest.mark.asyncio
    async def test_create_corporate_action(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "RELIANCE",
            "action_date": "2024-06-01",
            "action_type": "split",
            "ratio_numerator": 1,
            "ratio_denominator": 10,
            "adjustment_factor": 0.1,
        }
        resp = await client.post("/api/v1/corporate-actions", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol"] == "RELIANCE"
        assert data["action_type"] == "split"

    @pytest.mark.asyncio
    async def test_create_duplicate_returns_409(self, client: AsyncClient) -> None:
        payload = {"symbol": "TCS", "action_date": "2024-05-15", "action_type": "dividend", "dividend_amount": 28.0}
        resp1 = await client.post("/api/v1/corporate-actions", json=payload)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/corporate-actions", json=payload)
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_list_corporate_actions(self, client: AsyncClient) -> None:
        await client.post("/api/v1/corporate-actions", json={"symbol": "ITC", "action_date": "2024-01-01", "action_type": "dividend", "dividend_amount": 10.0})
        await client.post("/api/v1/corporate-actions", json={"symbol": "ITC", "action_date": "2024-06-01", "action_type": "split", "ratio_numerator": 1, "ratio_denominator": 5})
        resp = await client.get("/api/v1/corporate-actions/ITC")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_delete_corporate_action(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/corporate-actions", json={"symbol": "DEL", "action_date": "2024-01-01", "action_type": "other"})
        action_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/corporate-actions/{action_id}")
        assert resp.status_code == 200
