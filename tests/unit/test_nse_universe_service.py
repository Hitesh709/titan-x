import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.services.company_service import CompanyService
from titan_x.services.nse_universe_service import NSEUniverseService
from titan_x.models import *  # noqa: F401, F403 - register all models

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"

CSV_SAMPLE = (
    "SYMBOL,NAME OF COMPANY,ISIN NUMBER,SERIES\n"
    "RELIANCE,Reliance Industries Ltd,INE002A01018,EQ\n"
    "XYZCORP,XYZ Corp,INE000000000,BE\n"
)


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_fetch_failure_falls_back_to_curated_universe(session_factory, monkeypatch):
    async def boom(self):
        raise RuntimeError("NSE unreachable")

    monkeypatch.setattr(NSEUniverseService, "_fetch_csv", boom)

    async with session_factory() as session:
        result = await NSEUniverseService(session).load_universe()
        await session.commit()
        assert result["source"] == "fallback"
        assert result["added"] == 26

        companies, total = await CompanyService(session).list(search="RELIANCE", exchange="NSE")
        assert total == 1
        assert companies[0].symbol == "RELIANCE"
        assert companies[0].company_name == "Reliance Industries Ltd"


async def test_nse_csv_used_when_available(session_factory, monkeypatch):
    async def fake_csv(self):
        return CSV_SAMPLE

    monkeypatch.setattr(NSEUniverseService, "_fetch_csv", fake_csv)

    async with session_factory() as session:
        result = await NSEUniverseService(session).load_universe()
        await session.commit()
        assert result["source"] == "nse"
        # Only the EQ-series symbol is inserted; the BE row is skipped.
        assert result["added"] == 1

        _, total = await CompanyService(session).list(exchange="NSE")
        assert total == 1


async def test_fallback_is_idempotent(session_factory, monkeypatch):
    async def boom(self):
        raise RuntimeError("NSE unreachable")

    monkeypatch.setattr(NSEUniverseService, "_fetch_csv", boom)

    async with session_factory() as session:
        first = await NSEUniverseService(session).load_universe()
        await session.commit()
        second = await NSEUniverseService(session).load_universe()
        await session.commit()
        assert first["added"] == 26
        assert second["kept"] == 26
        assert second["added"] == 0