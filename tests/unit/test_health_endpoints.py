import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_returns_alive(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


@pytest.mark.skip(reason="Readiness check requires PostgreSQL features")
@pytest.mark.asyncio
async def test_readiness_returns_ready_when_everything_healthy(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "ready", "database": "available", "redis": "available"}
