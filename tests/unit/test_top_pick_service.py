from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.services.top_pick_service import TopPickService

N_DAYS = 260


def _seed(session: AsyncSession, symbol: str, trend: str) -> None:
    session.add(
        Company(
            symbol=symbol,
            company_name=f"{symbol} Ltd",
            isin=f"INE{symbol[:8]:0<8}",
            exchange="NSE",
            sector="Technology",
            market_cap=2_000_000_000_000,
            status="active",
        )
    )
    base = 1000.0
    start = date.today() - timedelta(days=N_DAYS)
    for i in range(N_DAYS):
        factor = 1.001 if trend == "up" else (0.999 if trend == "down" else 1.0)
        close = base * (factor**i)
        session.add(
            DailyPrice(
                symbol=symbol,
                trade_date=start + timedelta(days=i),
                open=close * 0.99,
                high=close * 1.02,
                low=close * 0.98,
                close=close,
                volume=1_000_000 + i * 1000,
            )
        )


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


class TestTopPickService:
    @pytest.mark.asyncio
    async def test_insufficient_history_is_skipped(self, session: AsyncSession) -> None:
        session.add(
            Company(
                symbol="NEW.NS",
                company_name="New Co",
                isin="INE000000001",
                exchange="NSE",
                status="active",
            )
        )
        session.add(
            DailyPrice(
                symbol="NEW.NS",
                trade_date=date.today(),
                open=10.0,
                high=11.0,
                low=9.0,
                close=10.0,
                volume=1000,
            )
        )
        await session.commit()
        result = await TopPickService(session).get_top_picks(limit=10)
        assert result["scored"] == 0
        assert result["top_picks"] == []

    @pytest.mark.asyncio
    async def test_uptrend_scores_above_downtrend(self, session: AsyncSession) -> None:
        _seed(session, "UPCO.NS", trend="up")
        _seed(session, "DOWNCO.NS", trend="down")
        await session.commit()

        result = await TopPickService(session).get_top_picks(limit=10)
        assert result["scored"] == 2
        picks = {p["symbol"]: p for p in result["top_picks"]}
        assert picks["UPCO.NS"]["composite"] > picks["DOWNCO.NS"]["composite"]

    @pytest.mark.asyncio
    async def test_all_six_layers_present(self, session: AsyncSession) -> None:
        _seed(session, "LAYERCO.NS", trend="up")
        await session.commit()

        result = await TopPickService(session).get_top_picks(limit=10)
        pick = result["top_picks"][0]
        for key in ("trend", "smart_money", "fundamentals", "news", "regime", "risk"):
            assert key in pick["layers"]
            assert "score" in pick["layers"][key]
            assert "signal" in pick["layers"][key]
            assert "evidence" in pick["layers"][key]

    @pytest.mark.asyncio
    async def test_limit_is_respected(self, session: AsyncSession) -> None:
        for i in range(5):
            _seed(session, f"CO{i:03d}.NS", trend="up")
        await session.commit()

        result = await TopPickService(session).get_top_picks(limit=3)
        assert len(result["top_picks"]) == 3

    @pytest.mark.asyncio
    async def test_risk_filter_flags_overbought(self, session: AsyncSession) -> None:
        # Single price that ends with a large spike => high RSI, drawdown check
        symbol = "SPIKECO.NS"
        session.add(
            Company(
                symbol=symbol,
                company_name="Spike Co",
                isin="INE000000099",
                exchange="NSE",
                status="active",
            )
        )
        start = date.today() - timedelta(days=N_DAYS)
        close = 100.0
        for i in range(N_DAYS):
            if i == N_DAYS - 3:
                close = 180.0
            session.add(
                DailyPrice(
                    symbol=symbol,
                    trade_date=start + timedelta(days=i),
                    open=close * 0.99,
                    high=close * 1.01,
                    low=close * 0.99,
                    close=close,
                    volume=1_000_000,
                )
            )
        await session.commit()

        result = await TopPickService(session).get_top_picks(limit=10)
        pick = next(p for p in result["top_picks"] if p["symbol"] == symbol)
        assert pick["layers"]["risk"]["score"] < 100
