import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_version_returns_app_version(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "build_date" in data
    assert "environment" in data
    assert data["environment"] == "test"
