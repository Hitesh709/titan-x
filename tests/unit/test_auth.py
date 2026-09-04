import pytest
from httpx import ASGITransport, AsyncClient

from titan_x.core.config import Settings, get_settings


@pytest.mark.asyncio
async def test_health_live_is_public_for_render_probe() -> None:
    from titan_x.main import app

    original_settings = get_settings()
    test_settings = Settings(
        database_url="sqlite+aiosqlite:///",
        redis_url="redis://localhost:6379/0",
        api_key="a" * 32,
        jwt_secret_key="b" * 32,
        environment="test",
    )
    app.dependency_overrides[get_settings] = lambda: test_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"

    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: original_settings
