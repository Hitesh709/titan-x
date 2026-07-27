"""Tests for Fundamental Scanner service."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.fundamental_scanner import FundamentalScanResult
from titan_x.services.fundamental_scanner_service import FundamentalScannerService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    SessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def service(session):
    return FundamentalScannerService(session)


@pytest_asyncio.fixture
async def company(session):
    c = Company(symbol="RELIANCE", company_name="Reliance Industries Ltd", isin="INE002A01018", exchange="NSE", status="active")
    session.add(c)
    await session.commit()
    return c


def _seed_metric(session, symbol: str, metric_name: str, value: float, fiscal_year: int = 2025, period_type: str = "annual"):
    m = FundamentalMetric(
        symbol=symbol, fiscal_year=fiscal_year, fiscal_period=4,
        period_type=period_type, metric_name=metric_name, value=value,
    )
    session.add(m)
    return m


class TestScorers:
    def test_roe_exceptional(self, service: FundamentalScannerService):
        result = service._score_roe(30.0)
        assert result["signal"] == "strong_bullish"
        assert result["score"] == 95

    def test_roe_strong(self, service: FundamentalScannerService):
        result = service._score_roe(20.0)
        assert result["signal"] == "bullish"
        assert result["score"] == 80

    def test_roe_good(self, service: FundamentalScannerService):
        result = service._score_roe(14.0)
        assert result["signal"] == "bullish"
        assert result["score"] == 65

    def test_roe_adequate(self, service: FundamentalScannerService):
        result = service._score_roe(10.0)
        assert result["signal"] == "neutral"
        assert result["score"] == 50

    def test_roe_weak(self, service: FundamentalScannerService):
        result = service._score_roe(5.0)
        assert result["signal"] == "bearish"
        assert result["score"] == 30

    def test_roe_negative(self, service: FundamentalScannerService):
        result = service._score_roe(-5.0)
        assert result["signal"] == "strong_bearish"
        assert result["score"] == 10

    def test_roe_none(self, service: FundamentalScannerService):
        result = service._score_roe(None)
        assert result["signal"] == "neutral"
        assert result["score"] == 0

    def test_roce_exceptional(self, service: FundamentalScannerService):
        result = service._score_roce(30.0)
        assert result["signal"] == "strong_bullish"
        assert result["score"] == 95

    def test_roce_weak(self, service: FundamentalScannerService):
        result = service._score_roce(5.0)
        assert result["signal"] == "bearish"

    def test_roce_none(self, service: FundamentalScannerService):
        result = service._score_roce(None)
        assert result["signal"] == "neutral"

    def test_debt_very_low(self, service: FundamentalScannerService):
        result = service._score_debt(0.2)
        assert result["signal"] == "strong_bullish"
        assert result["score"] == 95

    def test_debt_low(self, service: FundamentalScannerService):
        result = service._score_debt(0.5)
        assert result["signal"] == "bullish"
        assert result["score"] == 80

    def test_debt_moderate(self, service: FundamentalScannerService):
        result = service._score_debt(1.2)
        assert result["signal"] == "neutral"
        assert result["score"] == 55

    def test_debt_high(self, service: FundamentalScannerService):
        result = service._score_debt(2.0)
        assert result["signal"] == "bearish"
        assert result["score"] == 30

    def test_debt_very_high(self, service: FundamentalScannerService):
        result = service._score_debt(4.0)
        assert result["signal"] == "strong_bearish"
        assert result["score"] == 10

    def test_debt_none(self, service: FundamentalScannerService):
        result = service._score_debt(None)
        assert result["signal"] == "neutral"

    def test_revenue_growth_exceptional(self, service: FundamentalScannerService):
        result = service._score_revenue_growth(40.0)
        assert result["signal"] == "strong_bullish"
        assert result["score"] == 95

    def test_revenue_growth_strong(self, service: FundamentalScannerService):
        result = service._score_revenue_growth(20.0)
        assert result["signal"] == "bullish"
        assert result["score"] == 80

    def test_revenue_growth_good(self, service: FundamentalScannerService):
        result = service._score_revenue_growth(10.0)
        assert result["signal"] == "bullish"
        assert result["score"] == 65

    def test_revenue_growth_positive(self, service: FundamentalScannerService):
        result = service._score_revenue_growth(5.0)
        assert result["signal"] == "neutral"
        assert result["score"] == 50

    def test_revenue_growth_decline(self, service: FundamentalScannerService):
        result = service._score_revenue_growth(-5.0)
        assert result["signal"] == "bearish"
        assert result["score"] == 25

    def test_revenue_growth_sharp_decline(self, service: FundamentalScannerService):
        result = service._score_revenue_growth(-15.0)
        assert result["signal"] == "strong_bearish"
        assert result["score"] == 5

    def test_eps_growth_exceptional(self, service: FundamentalScannerService):
        result = service._score_eps_growth(40.0)
        assert result["signal"] == "strong_bullish"
        assert result["score"] == 95

    def test_eps_growth_sharp_decline(self, service: FundamentalScannerService):
        result = service._score_eps_growth(-15.0)
        assert result["signal"] == "strong_bearish"
        assert result["score"] == 5

    def test_cash_flow_excellent(self, service: FundamentalScannerService):
        result = service._score_cash_flow(9.0)
        assert result["signal"] == "strong_bullish"
        assert result["score"] == 95

    def test_cash_flow_good(self, service: FundamentalScannerService):
        result = service._score_cash_flow(7.0)
        assert result["signal"] == "bullish"
        assert result["score"] == 75

    def test_cash_flow_average(self, service: FundamentalScannerService):
        result = service._score_cash_flow(5.0)
        assert result["signal"] == "neutral"
        assert result["score"] == 50

    def test_cash_flow_weak(self, service: FundamentalScannerService):
        result = service._score_cash_flow(3.0)
        assert result["signal"] == "bearish"
        assert result["score"] == 25

    def test_cash_flow_poor(self, service: FundamentalScannerService):
        result = service._score_cash_flow(1.0)
        assert result["signal"] == "strong_bearish"
        assert result["score"] == 5

    def test_cash_flow_none(self, service: FundamentalScannerService):
        result = service._score_cash_flow(None)
        assert result["signal"] == "neutral"

    def test_valuation_attractive_pe(self, service: FundamentalScannerService):
        result = service._score_valuation(8.0, 0.8)
        assert result["signal"] == "bullish"
        assert result["score"] >= 80

    def test_valuation_expensive_pe(self, service: FundamentalScannerService):
        result = service._score_valuation(50.0, 8.0)
        assert result["signal"] == "strong_bearish"
        assert result["score"] == 25

    def test_valuation_no_data(self, service: FundamentalScannerService):
        result = service._score_valuation(None, None)
        assert result["signal"] == "neutral"
        assert result["score"] == 0

    def test_valuation_only_pe(self, service: FundamentalScannerService):
        result = service._score_valuation(12.0, None)
        assert result["signal"] == "neutral"

    def test_valuation_only_pb(self, service: FundamentalScannerService):
        result = service._score_valuation(None, 2.0)
        assert result["signal"] == "neutral"

    def test_valuation_negative_pe(self, service: FundamentalScannerService):
        result = service._score_valuation(-5.0, None)
        assert result["score"] == 5


class TestFullScan:
    async def test_scan_single_symbol(self, service: FundamentalScannerService, session, company):
        _seed_metric(session, "RELIANCE", "ROE", 22.5)
        _seed_metric(session, "RELIANCE", "ROCE", 20.0)
        _seed_metric(session, "RELIANCE", "DEBT_EQUITY", 0.45)
        _seed_metric(session, "RELIANCE", "REVENUE_GROWTH", 18.0)
        _seed_metric(session, "RELIANCE", "EPS_GROWTH", 25.0)
        _seed_metric(session, "RELIANCE", "QUALITY_SCORE", 8.5)
        _seed_metric(session, "RELIANCE", "PE", 15.0)
        _seed_metric(session, "RELIANCE", "PB", 2.8)
        await session.commit()

        result = await service.scan_symbol("RELIANCE")
        assert result.symbol == "RELIANCE"
        assert result.composite_score > 0
        assert result.roe_score > 0
        assert result.roe_signal in ("strong_bullish", "bullish")
        assert result.roce_score > 0
        assert result.debt_score > 0
        assert result.revenue_growth_score > 0
        assert result.eps_growth_score > 0
        assert result.cash_flow_score > 0
        assert result.valuation_score > 0

    async def test_scan_all(self, service: FundamentalScannerService, session, company):
        c2 = Company(symbol="TCS", company_name="TCS Ltd", isin="INE467B01029", exchange="NSE", status="active")
        session.add(c2)
        for sym in ["RELIANCE", "TCS"]:
            _seed_metric(session, sym, "ROE", 20.0)
            _seed_metric(session, sym, "ROCE", 18.0)
            _seed_metric(session, sym, "DEBT_EQUITY", 0.5)
        await session.commit()

        results = await service.scan_all()
        assert len(results) == 2
        assert all(r.composite_score > 0 for r in results)

    async def test_scan_inactive_company_not_scanned(self, service: FundamentalScannerService, session):
        c = Company(symbol="INACTIVE", company_name="Inactive", isin="INE000000000", exchange="NSE", status="inactive")
        session.add(c)
        await session.commit()

        results = await service.scan_all()
        assert len(results) == 0

    async def test_scan_with_no_metrics(self, service: FundamentalScannerService, session, company):
        result = await service.scan_symbol("RELIANCE")
        assert result.symbol == "RELIANCE"
        assert result.composite_score == 0.0
        assert result.roe_score == 0.0
        assert result.roe_signal == "neutral"

    async def test_scan_partial_metrics(self, service: FundamentalScannerService, session, company):
        _seed_metric(session, "RELIANCE", "ROE", 22.0)
        _seed_metric(session, "RELIANCE", "DEBT_EQUITY", 0.5)
        await session.commit()

        result = await service.scan_symbol("RELIANCE")
        assert result.roe_score > 0
        assert result.debt_score > 0
        assert result.roce_score == 0.0
        assert result.roce_signal == "neutral"


class TestQueryMethods:
    async def test_get_rankings(self, service: FundamentalScannerService, session, company):
        today = date.today()
        r1 = FundamentalScanResult(
            symbol="RELIANCE", scan_date=today, composite_score=85.0,
            roe_score=90, roce_score=85, debt_score=80, revenue_growth_score=85,
            eps_growth_score=80, cash_flow_score=75, valuation_score=70,
            roe_signal="bullish",
        )
        r2 = FundamentalScanResult(
            symbol="TCS", scan_date=today, composite_score=45.0,
            roe_score=50, roce_score=40, debt_score=60, revenue_growth_score=30,
            eps_growth_score=25, cash_flow_score=55, valuation_score=65,
            eps_growth_signal="bearish",
        )
        session.add_all([r1, r2])
        await session.commit()

        rankings = await service.get_rankings(today)
        assert len(rankings) == 2
        assert rankings[0].composite_score == 85.0

        top = await service.get_rankings(today, min_score=50)
        assert len(top) == 1
        assert top[0].symbol == "RELIANCE"

    async def test_get_latest_scan(self, service: FundamentalScannerService, session, company):
        today = date.today()
        yesterday = today - timedelta(days=1)
        r1 = FundamentalScanResult(
            symbol="RELIANCE", scan_date=yesterday, composite_score=50.0,
            roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
            eps_growth_score=0, cash_flow_score=0, valuation_score=0,
        )
        r2 = FundamentalScanResult(
            symbol="RELIANCE", scan_date=today, composite_score=70.0,
            roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
            eps_growth_score=0, cash_flow_score=0, valuation_score=0,
        )
        session.add_all([r1, r2])
        await session.commit()

        latest = await service.get_latest_scan("RELIANCE")
        assert latest is not None
        assert latest.scan_date == today
        assert latest.composite_score == 70.0

    async def test_get_latest_scan_not_found(self, service: FundamentalScannerService):
        assert await service.get_latest_scan("NONEXISTENT") is None

    async def test_get_scan_history(self, service: FundamentalScannerService, session, company):
        today = date.today()
        for i in range(5):
            d = today - timedelta(days=i)
            session.add(FundamentalScanResult(
                symbol="RELIANCE", scan_date=d, composite_score=float(100 - i * 10),
                roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
                eps_growth_score=0, cash_flow_score=0, valuation_score=0,
            ))
        await session.commit()

        history = await service.get_scan_history("RELIANCE")
        assert len(history) == 5
        assert history[0].scan_date == today

    async def test_get_top_by_dimension(self, service: FundamentalScannerService, session, company):
        today = date.today()
        values = [
            ("RELIANCE", 95, "strong_bullish"),
            ("TCS", 75, "bullish"),
            ("INFY", 30, "neutral"),
        ]
        for sym, score, sig in values:
            session.add(FundamentalScanResult(
                symbol=sym, scan_date=today, composite_score=score,
                roe_score=score, roce_score=0, debt_score=0, revenue_growth_score=0,
                eps_growth_score=0, cash_flow_score=0, valuation_score=0,
                roe_signal=sig,
            ))
        await session.commit()

        top = await service.get_top_by_dimension("roe", today, limit=2)
        assert len(top) == 2
        assert top[0].symbol == "RELIANCE"
        assert top[0].roe_score == 95

    async def test_get_all_scan_dates(self, service: FundamentalScannerService, session, company):
        today = date.today()
        yesterday = today - timedelta(days=1)
        session.add_all([
            FundamentalScanResult(
                symbol="RELIANCE", scan_date=today, composite_score=50,
                roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
                eps_growth_score=0, cash_flow_score=0, valuation_score=0,
            ),
            FundamentalScanResult(
                symbol="TCS", scan_date=yesterday, composite_score=50,
                roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
                eps_growth_score=0, cash_flow_score=0, valuation_score=0,
            ),
        ])
        await session.commit()

        dates = await service.get_all_scan_dates()
        assert len(dates) == 2
        assert dates[0] == today

    async def test_get_scan_summary(self, service: FundamentalScannerService, session, company):
        today = date.today()
        session.add_all([
            FundamentalScanResult(
                symbol="RELIANCE", scan_date=today, composite_score=85,
                roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
                eps_growth_score=0, cash_flow_score=0, valuation_score=0,
            ),
            FundamentalScanResult(
                symbol="TCS", scan_date=today, composite_score=55,
                roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
                eps_growth_score=0, cash_flow_score=0, valuation_score=0,
            ),
            FundamentalScanResult(
                symbol="INFY", scan_date=today, composite_score=30,
                roe_score=0, roce_score=0, debt_score=0, revenue_growth_score=0,
                eps_growth_score=0, cash_flow_score=0, valuation_score=0,
            ),
        ])
        await session.commit()

        summary = await service.get_scan_summary(today)
        assert summary["total_scanned"] == 3
        assert summary["strong_count"] == 1  # score >= 75
        assert summary["weak_count"] == 1   # score <= 40
        assert summary["avg_composite_score"] > 0
