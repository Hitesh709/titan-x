"""End-to-end Screener API coverage using the project's real FastAPI app and service."""

from datetime import date

import pytest
from sqlalchemy import select

from titan_x.api import deps
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.user import User


@pytest.mark.asyncio
async def test_screener_run_uses_real_api_and_service(client, app):
    """Exercise HTTP -> FastAPI dependency -> AdvancedScreenerService -> DB."""
    session_factory = app.state.session_factory
    async with session_factory() as session:
        user = User(
            email="screener.integration@example.com",
            hashed_password="test-hash",
            is_active=True,
            is_verified=True,
            role="normal",
        )
        company = Company(
            symbol="TSTINTEG",
            company_name="TITAN X Integration Test",
            isin="TESTINTEG01",
            exchange="NSE",
            sector="Technology",
            status="active",
            market_cap=10_000_000,
        )
        price = DailyPrice(
            symbol="TSTINTEG",
            trade_date=date(2025, 6, 30),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=100_000,
        )
        session.add_all([user, company, price])
        await session.commit()
        await session.refresh(user)

    async def _current_user():
        async with session_factory() as session:
            return await session.scalar(select(User).where(User.id == user.id))

    app.dependency_overrides[deps.get_current_active_user] = _current_user

    response = await client.post(
        "/api/v1/screener/run?limit=10&as_of_date=2025-06-30",
        json={},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["limit"] == 10
    assert any(item["symbol"] == "TSTINTEG" for item in payload["results"])

    result = next(item for item in payload["results"] if item["symbol"] == "TSTINTEG")
    assert result["as_of_date"] == "2025-06-30"
    assert "titan_x_score" in result
    assert 0 <= result["titan_x_score"] <= 100
    assert "score_breakdown" in result
    assert "why_passed" in result
