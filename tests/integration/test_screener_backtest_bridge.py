"""Integration coverage for the saved Screener -> Backtest API bridge."""

import json
from datetime import date

from sqlalchemy import select

from titan_x.api import deps
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.saved_screen import SavedScreen
from titan_x.models.user import User


async def test_saved_screen_can_launch_backtest_for_current_result(client, app, monkeypatch):
    """Verify the real Screener path gates and launches the canonical engine."""
    session_factory = app.state.session_factory
    async with session_factory() as session:
        user = User(
            email="screener.backtest.integration@example.com",
            hashed_password="test-hash",
            is_active=True,
            is_verified=True,
            role="normal",
        )
        company = Company(
            symbol="TSTBACKTEST",
            company_name="TITAN X Backtest Integration Test",
            isin="TESTBACKTEST01",
            exchange="NSE",
            sector="Technology",
            status="active",
            market_cap=10_000_000,
        )
        price = DailyPrice(
            symbol="TSTBACKTEST",
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

        screen = SavedScreen(
            user_id=user.id,
            name="Integration Screen",
            description="Backtest bridge integration screen",
            filters_json=json.dumps({}),
        )
        session.add(screen)
        await session.commit()
        await session.refresh(screen)
        screen_id = screen.id
        user_id = user.id

    async def _current_user():
        async with session_factory() as session:
            return await session.scalar(select(User).where(User.id == user_id))

    app.dependency_overrides[deps.get_current_active_user] = _current_user

    class StubBacktestEngine:
        def __init__(self, _session):
            pass

        async def create_backtest(self, **kwargs):
            assert kwargs["symbol"] == "TSTBACKTEST"
            assert kwargs["user_id"] == user_id
            return {"id": 987, "symbol": "TSTBACKTEST", "status": "draft"}

        async def run_backtest(self, backtest_id):
            assert backtest_id == 987
            return {
                "backtest_id": 987,
                "status": "completed",
                "metrics": {"total_return_pct": 2.5},
                "trades_count": 1,
                "equity_points": 1,
            }

    monkeypatch.setattr("titan_x.api.v1.advanced_screener.BacktestEngine", StubBacktestEngine)

    response = await client.post(
        f"/api/v1/screener/screens/{screen_id}/backtest",
        json={
            "screen_id": screen_id,
            "symbol": "TSTBACKTEST",
            "start_date": "2025-06-01",
            "end_date": "2025-06-30",
            "initial_capital": 10000,
            "strategy_type": "sma_crossover",
            "strategy_params": {},
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["screen_id"] == screen_id
    assert payload["symbol"] == "TSTBACKTEST"
    assert payload["backtest"]["id"] == 987
    assert payload["result"]["status"] == "completed"


async def test_saved_screen_backtest_rejects_symbol_not_in_current_result(client, app):
    """A stale or unrelated frontend symbol must never reach the engine."""
    session_factory = app.state.session_factory
    async with session_factory() as session:
        user = User(
            email="screener.backtest.reject@example.com",
            hashed_password="test-hash",
            is_active=True,
            is_verified=True,
            role="normal",
        )
        company = Company(
            symbol="TSTCURRENT",
            company_name="TITAN X Current Result Test",
            isin="TESTCURRENT01",
            exchange="NSE",
            sector="Technology",
            status="active",
            market_cap=10_000_000,
        )
        price = DailyPrice(
            symbol="TSTCURRENT",
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
        screen = SavedScreen(
            user_id=user.id,
            name="Reject Screen",
            filters_json=json.dumps({}),
        )
        session.add(screen)
        await session.commit()
        await session.refresh(screen)
        screen_id = screen.id
        user_id = user.id

    async def _current_user():
        async with session_factory() as session:
            return await session.scalar(select(User).where(User.id == user_id))

    app.dependency_overrides[deps.get_current_active_user] = _current_user

    response = await client.post(
        f"/api/v1/screener/screens/{screen_id}/backtest",
        json={
            "screen_id": screen_id,
            "symbol": "NOT_IN_SCREEN",
            "start_date": "2025-06-01",
            "end_date": "2025-06-30",
            "initial_capital": 10000,
        },
    )

    assert response.status_code == 400
    assert "not present" in response.json()["detail"]
