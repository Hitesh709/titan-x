import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.backtest import Backtest, BacktestEquityPoint, BacktestReport, BacktestSignal, BacktestTrade
from titan_x.models.price import DailyPrice
from titan_x.models.user import User
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.performance_analyzer import PerformanceAnalyzer


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        await sess.execute(select(1).where(True))
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    u = User(email="bt@test.com", hashed_password="h")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
async def price_data(session: AsyncSession) -> None:
    today = date.today()
    for i in range(200):
        close = 100.0 + (i % 50) * 2.0 if (i // 50) % 2 == 0 else 200.0 - (i % 50) * 2.0
        dp = DailyPrice(
            symbol="TEST",
            trade_date=today - timedelta(days=199 - i),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1_000_000,
        )
        session.add(dp)
    await session.flush()


@pytest_asyncio.fixture
async def engine(session: AsyncSession) -> BacktestEngine:
    return BacktestEngine(session)


class TestCreateBacktest:
    @pytest.mark.asyncio
    async def test_create_backtest(self, engine: BacktestEngine, user: User):
        result = await engine.create_backtest(
            user_id=user.id, name="Test BT", symbol="TEST",
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
        )
        assert result["name"] == "Test BT"
        assert result["symbol"] == "TEST"
        assert result["status"] == "draft"
        assert result["initial_capital"] == 10000.0
        assert result["strategy_type"] == "sma_crossover"
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_create_with_custom_params(self, engine: BacktestEngine, user: User):
        result = await engine.create_backtest(
            user_id=user.id, name="RSI BT", symbol="AAPL",
            start_date=date(2025, 1, 1), end_date=date(2025, 3, 31),
            initial_capital=50000.0, strategy_type="rsi",
            strategy_params={"oversold": 25, "overbought": 75},
        )
        assert result["strategy_type"] == "rsi"
        params = json.loads(result["strategy_params_json"])
        assert params["oversold"] == 25
        assert params["overbought"] == 75


class TestRunBacktest:
    @pytest.mark.asyncio
    async def test_run_sma_crossover(self, engine: BacktestEngine, session: AsyncSession, user: User, price_data):
        bt = await engine.create_backtest(
            user_id=user.id, name="SMA Test", symbol="TEST",
            start_date=date.today() - timedelta(days=180),
            end_date=date.today(),
            strategy_type="sma_crossover",
            strategy_params={"fast_period": 5, "slow_period": 20},
        )
        result = await engine.run_backtest(bt["id"])
        assert result["status"] == "completed"
        assert result["trades_count"] > 0
        assert result["equity_points"] > 0

        trades = await engine.get_trades(bt["id"])
        assert len(trades) > 0
        assert trades[0].backtest_id == bt["id"]
        assert trades[0].status in ("open", "closed")

        curve = await engine.get_equity_curve(bt["id"])
        assert len(curve) > 0
        assert curve[0].backtest_id == bt["id"]
        assert curve[-1].equity > 0

        signals = await engine.get_signals(bt["id"])
        assert len(signals) > 0

    @pytest.mark.asyncio
    async def test_run_rsi_strategy(self, engine: BacktestEngine, session: AsyncSession, user: User, price_data):
        bt = await engine.create_backtest(
            user_id=user.id, name="RSI Test", symbol="TEST",
            start_date=date.today() - timedelta(days=180),
            end_date=date.today(),
            strategy_type="rsi",
        )
        result = await engine.run_backtest(bt["id"])
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_bollinger_strategy(self, engine: BacktestEngine, session: AsyncSession, user: User, price_data):
        bt = await engine.create_backtest(
            user_id=user.id, name="BB Test", symbol="TEST",
            start_date=date.today() - timedelta(days=180),
            end_date=date.today(),
            strategy_type="bollinger",
        )
        result = await engine.run_backtest(bt["id"])
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_custom_signals(self, engine: BacktestEngine, session: AsyncSession, user: User, price_data):
        today = date.today()
        signals = [
            {"date": (today - timedelta(days=150)).isoformat(), "action": "buy", "price": 175.0},
            {"date": (today - timedelta(days=100)).isoformat(), "action": "sell", "price": 225.0},
            {"date": (today - timedelta(days=50)).isoformat(), "action": "buy", "price": 250.0},
        ]
        bt = await engine.create_backtest(
            user_id=user.id, name="Custom Test", symbol="TEST",
            start_date=today - timedelta(days=180), end_date=today,
            strategy_type="custom",
            strategy_params={"signals": signals},
        )
        result = await engine.run_backtest(bt["id"])
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_creates_report(self, engine: BacktestEngine, session: AsyncSession, user: User, price_data):
        bt = await engine.create_backtest(
            user_id=user.id, name="Report Test", symbol="TEST",
            start_date=date.today() - timedelta(days=180),
            end_date=date.today(),
        )
        await engine.run_backtest(bt["id"])

        reports = await session.execute(
            select(BacktestReport).where(BacktestReport.backtest_id == bt["id"])
        )
        report = reports.scalar_one_or_none()
        assert report is not None
        assert report.total_trades >= 0
        assert report.win_rate >= 0
        assert report.starting_equity == 10000.0
        assert report.ending_equity > 0

    @pytest.mark.asyncio
    async def test_run_nonexistent_backtest(self, engine: BacktestEngine):
        with pytest.raises(ValueError, match="not found"):
            await engine.run_backtest(9999)

    @pytest.mark.asyncio
    async def test_run_insufficient_data(self, engine: BacktestEngine, session: AsyncSession, user: User):
        bt = await engine.create_backtest(
            user_id=user.id, name="No Data", symbol="NODATA",
            start_date=date(2025, 1, 1), end_date=date(2025, 1, 10),
        )
        with pytest.raises(ValueError, match="Insufficient price data"):
            await engine.run_backtest(bt["id"])


class TestGetBacktest:
    @pytest.mark.asyncio
    async def test_get_backtest(self, engine: BacktestEngine, user: User):
        bt = await engine.create_backtest(
            user_id=user.id, name="Get Test", symbol="TEST",
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
        )
        result = await engine.get_backtest(bt["id"])
        assert result is not None
        assert result["name"] == "Get Test"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, engine: BacktestEngine):
        result = await engine.get_backtest(9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_report(self, engine: BacktestEngine, session: AsyncSession, user: User, price_data):
        bt = await engine.create_backtest(
            user_id=user.id, name="Report", symbol="TEST",
            start_date=date.today() - timedelta(days=180),
            end_date=date.today(),
        )
        await engine.run_backtest(bt["id"])
        result = await engine.get_backtest_with_report(bt["id"])
        assert result is not None
        assert "report" in result
        assert result["report"] is not None
        assert result["report"]["total_trades"] >= 0
        assert result["report"]["win_rate"] >= 0

    @pytest.mark.asyncio
    async def test_list_backtests(self, engine: BacktestEngine, user: User):
        for i in range(3):
            await engine.create_backtest(
                user_id=user.id, name=f"BT {i}", symbol="TEST",
                start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
            )
        rows, total = await engine.list_backtests(user_id=user.id)
        assert total == 3
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_delete_backtest(self, engine: BacktestEngine, user: User):
        bt = await engine.create_backtest(
            user_id=user.id, name="Del", symbol="TEST",
            start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
        )
        deleted = await engine.delete_backtest(bt["id"])
        assert deleted is True
        result = await engine.get_backtest(bt["id"])
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, engine: BacktestEngine):
        deleted = await engine.delete_backtest(9999)
        assert deleted is False


class TestPerformanceAnalyzer:
    def factory(self) -> PerformanceAnalyzer:
        return PerformanceAnalyzer()

    def test_calculate_pnl_empty(self):
        pa = self.factory()
        result = pa.calculate_pnl([])
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0

    def test_calculate_pnl_with_trades(self):
        pa = self.factory()
        trades = [
            {"status": "closed", "pnl": 100.0, "pnl_pct": 5.0, "holding_days": 10},
            {"status": "closed", "pnl": -50.0, "pnl_pct": -2.5, "holding_days": 5},
            {"status": "closed", "pnl": 200.0, "pnl_pct": 10.0, "holding_days": 15},
        ]
        result = pa.calculate_pnl(trades)
        assert result["total_trades"] == 3
        assert result["winning_trades"] == 2
        assert result["losing_trades"] == 1
        assert result["win_rate"] == 2 / 3 * 100
        assert result["profit_factor"] == 300.0 / 50.0
        assert result["avg_win"] == 150.0
        assert result["avg_loss"] == -50.0
        assert result["best_trade_pnl"] == 200.0
        assert result["worst_trade_pnl"] == -50.0

    def test_calculate_drawdown(self):
        pa = self.factory()
        curve = [
            {"equity": 10000.0},
            {"equity": 11000.0},
            {"equity": 10500.0},
            {"equity": 12000.0},
            {"equity": 11500.0},
        ]
        result = pa.calculate_drawdown(curve)
        assert result["max_drawdown"] == 500.0
        assert result["max_drawdown_pct"] == pytest.approx(500.0 / 11000.0 * 100)

    def test_calculate_drawdown_empty(self):
        pa = self.factory()
        result = pa.calculate_drawdown([])
        assert result["max_drawdown"] == 0.0

    def test_calculate_sharpe(self):
        pa = self.factory()
        returns = [0.01, 0.02, -0.01, 0.015, -0.005, 0.01]
        sharpe = pa.calculate_sharpe(returns)
        assert sharpe is not None
        assert sharpe > -10

    def test_calculate_sharpe_insufficient(self):
        pa = self.factory()
        assert pa.calculate_sharpe([]) is None
        assert pa.calculate_sharpe([0.01]) is None

    def test_calculate_sortino(self):
        pa = self.factory()
        returns = [0.01, 0.02, -0.01, 0.015, -0.005, 0.01]
        sortino = pa.calculate_sortino(returns)
        assert sortino is not None
        assert sortino > -10

    def test_calculate_sortino_no_downside(self):
        pa = self.factory()
        returns = [0.01, 0.02, 0.015]
        result = pa.calculate_sortino(returns)
        assert result is None

    def test_calculate_calmar(self):
        pa = self.factory()
        result = pa.calculate_calmar(15.0, 10.0)
        assert result == pytest.approx(1.5)

    def test_calculate_calmar_zero_drawdown(self):
        pa = self.factory()
        assert pa.calculate_calmar(10.0, 0.0) is None

    def test_calculate_annualized_return(self):
        pa = self.factory()
        result = pa.calculate_annualized_return(
            10000.0, 15000.0,
            date(2025, 1, 1), date(2026, 1, 1),
        )
        assert result is not None
        assert result > 0

    def test_equity_curve_generation(self):
        pa = self.factory()
        dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(10)]
        closes = [100.0 + i for i in range(10)]
        trades = [
            {
                "status": "closed",
                "entry_date": dates[2], "exit_date": dates[5],
                "entry_price": 102.0, "exit_price": 105.0,
                "quantity": 50, "symbol": "TEST", "side": "long",
                "pnl": 150.0, "pnl_pct": 2.94, "holding_days": 3,
                "commission": 0.0, "slippage": 0.0,
            },
        ]
        curve = pa.generate_equity_curve(dates, closes, trades, 10000.0)
        assert len(curve) == len(dates)
        assert curve[0]["equity"] == 10000.0
        assert curve[-1]["equity"] > 0

    def test_compute_all_metrics(self):
        pa = self.factory()
        trades = [
            {"status": "closed", "pnl": 200.0, "pnl_pct": 2.0, "holding_days": 5, "commission": 5.0, "slippage": 2.0},
            {"status": "closed", "pnl": -50.0, "pnl_pct": -1.0, "holding_days": 3, "commission": 5.0, "slippage": 2.0},
        ]
        start_d = date(2025, 1, 1)
        end_d = date(2025, 6, 30)
        curve = [
            {"date": start_d, "equity": 10000.0, "cash": 10000.0, "holdings_value": 0.0, "returns_pct": 0.0, "drawdown_pct": 0.0},
            {"date": end_d, "equity": 10150.0, "cash": 10150.0, "holdings_value": 0.0, "returns_pct": 1.5, "drawdown_pct": 0.0},
        ]
        metrics = pa.compute_all_metrics(trades, curve, 10000.0, 10150.0, start_d, end_d)
        assert metrics["total_trades"] == 2
        assert metrics["total_commission"] == 10.0
        assert metrics["total_slippage"] == 4.0
        assert metrics["starting_equity"] == 10000.0
        assert metrics["ending_equity"] == 10150.0


class TestSMA:
    @pytest.mark.asyncio
    async def test_sma(self, engine: BacktestEngine):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = engine._sma(data, 3)
        assert result[:2] == [None, None]
        assert result[2] == pytest.approx(2.0)
        assert result[3] == pytest.approx(3.0)
        assert result[4] == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_sma_period_too_long(self, engine: BacktestEngine):
        data = [1.0, 2.0]
        result = engine._sma(data, 5)
        assert all(r is None for r in result)

    @pytest.mark.asyncio
    async def test_rsi(self, engine: BacktestEngine):
        data = [100.0, 102.0, 101.0, 103.0, 104.0, 102.0, 105.0, 106.0, 104.0, 107.0,
                108.0, 106.0, 109.0, 110.0, 108.0, 111.0]
        result = engine._rsi(data, 14)
        assert result[14] is not None
        assert 0 <= result[14] <= 100
