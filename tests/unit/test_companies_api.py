import pytest
from httpx import AsyncClient


class TestCompaniesAPI:
    @pytest.mark.asyncio
    async def test_create_company(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "RELIANCE",
            "company_name": "Reliance Industries Ltd",
            "isin": "INE002A01018",
            "exchange": "NSE",
            "sector": "Conglomerate",
            "industry": "Diversified",
            "market_cap": 17000000000000,
            "listing_date": "2000-01-01",
        }
        resp = await client.post("/api/v1/companies", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol"] == "RELIANCE"
        assert data["isin"] == "INE002A01018"
        assert data["exchange"] == "NSE"

    @pytest.mark.asyncio
    async def test_create_duplicate_returns_409(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "TCS",
            "company_name": "Tata Consultancy Services",
            "isin": "INE467B01029",
            "exchange": "NSE",
        }
        resp1 = await client.post("/api/v1/companies", json=payload)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/companies", json=payload)
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_get_company(self, client: AsyncClient) -> None:
        payload = {
            "symbol": "INFY",
            "company_name": "Infosys Ltd",
            "isin": "INE009A01021",
            "exchange": "NSE",
        }
        create_resp = await client.post("/api/v1/companies", json=payload)
        company_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/companies/{company_id}")
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "INFY"

    @pytest.mark.asyncio
    async def test_get_company_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/companies/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_companies(self, client: AsyncClient) -> None:
        await client.post("/api/v1/companies", json={"symbol": "A", "company_name": "A Ltd", "isin": "INE000A01001", "exchange": "NSE"})
        await client.post("/api/v1/companies", json={"symbol": "B", "company_name": "B Ltd", "isin": "INE000A01002", "exchange": "BSE"})
        resp = await client.get("/api/v1/companies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_companies_with_filters(self, client: AsyncClient) -> None:
        await client.post("/api/v1/companies", json={"symbol": "N1", "company_name": "NSE Co", "isin": "INE000A01003", "exchange": "NSE", "sector": "Tech"})
        await client.post("/api/v1/companies", json={"symbol": "B1", "company_name": "BSE Co", "isin": "INE000A01004", "exchange": "BSE", "sector": "Finance"})
        resp = await client.get("/api/v1/companies?exchange=BSE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["exchange"] == "BSE"

    @pytest.mark.asyncio
    async def test_list_companies_search(self, client: AsyncClient) -> None:
        await client.post("/api/v1/companies", json={"symbol": "TITAN", "company_name": "Titan Ltd", "isin": "INE280A01028", "exchange": "NSE"})
        await client.post("/api/v1/companies", json={"symbol": "TATA", "company_name": "Tata Ltd", "isin": "INE081A01020", "exchange": "NSE"})
        resp = await client.get("/api/v1/companies?search=TITAN")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_update_company(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/companies", json={"symbol": "MARUTI", "company_name": "Maruti Suzuki", "isin": "INE585B01010", "exchange": "NSE"})
        company_id = create_resp.json()["id"]
        resp = await client.patch(f"/api/v1/companies/{company_id}", json={"sector": "Automobile", "market_cap": 3000000000000})
        assert resp.status_code == 200
        assert resp.json()["sector"] == "Automobile"
        assert resp.json()["market_cap"] == 3000000000000

    @pytest.mark.asyncio
    async def test_update_company_not_found(self, client: AsyncClient) -> None:
        resp = await client.patch("/api/v1/companies/999", json={"sector": "Tech"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_company(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/companies", json={"symbol": "DEL", "company_name": "Delete Co", "isin": "INE000A01099", "exchange": "NSE"})
        company_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/companies/{company_id}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Company deleted"

    @pytest.mark.asyncio
    async def test_delete_company_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/v1/companies/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_by_symbol(self, client: AsyncClient) -> None:
        await client.post("/api/v1/companies", json={"symbol": "WIPRO", "company_name": "Wipro Ltd", "isin": "INE075A01022", "exchange": "NSE"})
        resp = await client.get("/api/v1/companies/by-symbol/WIPRO")
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "WIPRO"

    @pytest.mark.asyncio
    async def test_get_by_symbol_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/companies/by-symbol/UNKNOWN")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_by_isin(self, client: AsyncClient) -> None:
        await client.post("/api/v1/companies", json={"symbol": "ITC", "company_name": "ITC Ltd", "isin": "INE154A01025", "exchange": "NSE"})
        resp = await client.get("/api/v1/companies/by-isin/INE154A01025")
        assert resp.status_code == 200
        assert resp.json()["isin"] == "INE154A01025"

    @pytest.mark.asyncio
    async def test_get_by_isin_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/companies/by-isin/IN0000000000")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_meta_sectors(self, client: AsyncClient) -> None:
        await client.post("/api/v1/companies", json={"symbol": "S1", "company_name": "S1", "isin": "INE000A01050", "exchange": "NSE", "sector": "Tech"})
        await client.post("/api/v1/companies", json={"symbol": "S2", "company_name": "S2", "isin": "INE000A01051", "exchange": "NSE", "sector": "Finance"})
        resp = await client.get("/api/v1/companies/meta/sectors")
        assert resp.status_code == 200
        assert "Tech" in resp.json()

    @pytest.mark.asyncio
    async def test_list_meta_exchanges(self, client: AsyncClient) -> None:
        await client.post("/api/v1/companies", json={"symbol": "EX1", "company_name": "EX1", "isin": "INE000A01060", "exchange": "NSE"})
        await client.post("/api/v1/companies", json={"symbol": "EX2", "company_name": "EX2", "isin": "INE000A01061", "exchange": "BSE"})
        resp = await client.get("/api/v1/companies/meta/exchanges")
        assert resp.status_code == 200
        assert "NSE" in resp.json()
        assert "BSE" in resp.json()
