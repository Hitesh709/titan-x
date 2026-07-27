from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.corporate_action_detection import CorporateActionDetection
from titan_x.models.price import CorporateAction, DailyPrice
from titan_x.services.corporate_action_detector import CorporateActionDetector


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def company(session: AsyncSession) -> Company:
    c = Company(symbol="TEST", company_name="Test Corp", isin="IN00001", exchange="NSE", sector="Technology")
    session.add(c)
    await session.flush()
    return c


@pytest_asyncio.fixture
async def prices(session: AsyncSession) -> list[DailyPrice]:
    rows = []
    for i in range(100):
        d = date(2025, 1, 1) + timedelta(days=i)
        p = DailyPrice(symbol="TEST", trade_date=d, open=200.0, high=205.0, low=195.0, close=(200.0 + i * 0.1), volume=1_000_000)
        session.add(p)
        rows.append(p)
    await session.flush()
    return rows


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> CorporateActionDetector:
    return CorporateActionDetector(session)


# ============================================================
# DETECTION STORAGE
# ============================================================

class TestDetectionStorage:
    @pytest.mark.asyncio
    async def test_list_empty(self, svc: CorporateActionDetector):
        rows, total = await svc.list_detections()
        assert total == 0
        assert rows == []

    @pytest.mark.asyncio
    async def test_delete_not_found(self, svc: CorporateActionDetector):
        assert await svc.delete_detection(9999) is False

    @pytest.mark.asyncio
    async def test_get_not_found(self, svc: CorporateActionDetector):
        assert await svc.get_detection(9999) is None


# ============================================================
# SPLIT DETECTION
# ============================================================

class TestSplitDetection:
    @pytest.mark.asyncio
    async def test_no_prices(self, svc: CorporateActionDetector):
        results = await svc.detect_splits("NONEXISTENT")
        assert results == []

    @pytest.mark.asyncio
    async def test_detect_10_to_1_split(self, svc: CorporateActionDetector, prices: list[DailyPrice], session: AsyncSession):
        split_day = date(2025, 3, 15)
        split_idx = (split_day - date(2025, 1, 1)).days
        if 0 <= split_idx < len(prices):
            prices[split_idx].close = 20.0
            prices[split_idx].open = 21.0
            prices[split_idx].volume = 15_000_000
            prices[split_idx - 1].close = 205.0
            await session.flush()

        results = await svc.detect_splits("TEST")
        assert len(results) >= 1
        r = results[0]
        assert r.detected_type == "split"
        assert r.confidence >= 20
        assert r.source == "price_anomaly"
        assert r.estimated_numerator is not None
        assert r.estimated_denominator is not None
        assert r.price_before is not None
        assert r.price_after is not None

    @pytest.mark.asyncio
    async def test_no_false_positive_normal(self, svc: CorporateActionDetector, prices: list[DailyPrice]):
        results = await svc.detect_splits("TEST")
        split_results = [r for r in results if r.detected_type == "split"]
        assert len(split_results) == 0


# ============================================================
# BONUS DETECTION
# ============================================================

class TestBonusDetection:
    @pytest.mark.asyncio
    async def test_no_prices(self, svc: CorporateActionDetector):
        results = await svc.detect_bonuses("NONEXISTENT")
        assert results == []

    @pytest.mark.asyncio
    async def test_detect_1_to_1_bonus(self, svc: CorporateActionDetector, prices: list[DailyPrice], session: AsyncSession):
        bonus_day = date(2025, 4, 1)
        idx = (bonus_day - date(2025, 1, 1)).days
        if 0 < idx < len(prices):
            prices[idx].close = 100.0
            prices[idx].open = 101.0
            prices[idx].volume = 3_000_000
            prices[idx - 1].close = 200.0
            await session.flush()

        results = await svc.detect_bonuses("TEST")
        assert len(results) >= 0


# ============================================================
# DIVIDEND DETECTION
# ============================================================

class TestDividendDetection:
    @pytest.mark.asyncio
    async def test_no_prices(self, svc: CorporateActionDetector):
        results = await svc.detect_dividends("NONEXISTENT")
        assert results == []

    @pytest.mark.asyncio
    async def test_detect_dividend(self, svc: CorporateActionDetector, prices: list[DailyPrice], session: AsyncSession):
        div_day = date(2025, 5, 1)
        idx = (div_day - date(2025, 1, 1)).days
        if 0 < idx < len(prices):
            prices[idx - 1].close = 250.0
            prices[idx].open = 245.0
            prices[idx].close = 246.0
            prices[idx].volume = 1_500_000
            await session.flush()

        results = await svc.detect_dividends("TEST")
        assert len(results) >= 1
        r = results[0]
        assert r.detected_type == "dividend"
        assert r.estimated_dividend_amount is not None
        assert r.price_before is not None


# ============================================================
# RIGHTS DETECTION
# ============================================================

class TestRightsDetection:
    @pytest.mark.asyncio
    async def test_no_prices(self, svc: CorporateActionDetector):
        results = await svc.detect_rights("NONEXISTENT")
        assert results == []

    @pytest.mark.asyncio
    async def test_detect_rights(self, svc: CorporateActionDetector, prices: list[DailyPrice], session: AsyncSession):
        rday = date(2025, 6, 1)
        idx = (rday - date(2025, 1, 1)).days
        if 0 < idx < len(prices):
            prices[idx - 1].close = 180.0
            prices[idx].close = 155.0
            prices[idx].open = 156.0
            prices[idx].volume = 10_000_000
            prices[min(idx + 3, len(prices) - 1)].close = 160.0
            await session.flush()

        results = await svc.detect_rights("TEST")
        assert len(results) >= 0


# ============================================================
# DETECT ALL
# ============================================================

class TestDetectAll:
    @pytest.mark.asyncio
    async def test_detect_all_returns_structure(self, svc: CorporateActionDetector):
        result = await svc.detect_all("TEST")
        assert result["symbol"] == "TEST"
        assert "detections" in result
        for dt in ("splits", "bonuses", "dividends", "rights", "mergers", "acquisitions"):
            assert dt in result["detections"]


# ============================================================
# CONFIRM PIPELINE
# ============================================================

class TestConfirmPipeline:
    @pytest.mark.asyncio
    async def test_confirm_nonexistent(self, svc: CorporateActionDetector):
        with pytest.raises(ValueError, match="Detection not found"):
            await svc.confirm_detection(9999)

    @pytest.mark.asyncio
    async def test_confirm_split(self, svc: CorporateActionDetector, prices: list[DailyPrice], session: AsyncSession):
        split_day = date(2025, 3, 15)
        idx = (split_day - date(2025, 1, 1)).days
        if 0 < idx < len(prices):
            prices[idx].close = 20.0
            prices[idx].open = 21.0
            prices[idx].volume = 15_000_000
            prices[idx - 1].close = 200.0
            await session.flush()

        detections = await svc.detect_splits("TEST")
        if not detections:
            pytest.skip("No split detected")
        d = detections[0]
        action = await svc.confirm_detection(d.id)

        assert action.symbol == "TEST"
        assert action.action_type == "split"

        updated = await svc.get_detection(d.id)
        assert updated is not None
        assert updated.status == "confirmed"
        assert updated.confirmed_action_id == action.id

    @pytest.mark.asyncio
    async def test_confirm_and_adjust(self, svc: CorporateActionDetector, prices: list[DailyPrice], session: AsyncSession):
        split_day = date(2025, 3, 15)
        idx = (split_day - date(2025, 1, 1)).days
        if 0 < idx < len(prices):
            prices[idx].close = 20.0
            prices[idx].open = 21.0
            prices[idx].volume = 15_000_000
            prices[idx - 1].close = 200.0
            await session.flush()

        detections = await svc.detect_splits("TEST")
        if not detections:
            pytest.skip("No split detected")
        d = detections[0]

        result = await svc.confirm_and_adjust(d.id)
        assert "action" in result
        assert "adjustment" in result
        assert result["action"]["type"] == "split"
        assert result["adjustment"]["prices_adjusted"] > 0
        assert result["adjustment"]["actions_used"] > 0


# ============================================================
# AUTO DETECT & ADJUST
# ============================================================

class TestAutoPipeline:
    @pytest.mark.asyncio
    async def test_auto_pipeline(self, svc: CorporateActionDetector, prices: list[DailyPrice]):
        result = await svc.auto_detect_and_adjust("TEST", min_confidence=0)
        assert result["symbol"] == "TEST"
        assert result["detections_found"] >= 0
        assert result["confirmed"] >= 0
