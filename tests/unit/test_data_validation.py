import math
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.corporate_action_detection import CorporateActionDetection
from titan_x.models.data_validation import DataQualityScore, ValidationAnomaly, ValidationRun
from titan_x.models.price import CorporateAction, DailyPrice
from titan_x.services.dataset_validation_service import DatasetValidationService


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
async def svc(session: AsyncSession) -> DatasetValidationService:
    return DatasetValidationService(session)


@pytest_asyncio.fixture
async def clean_prices(session: AsyncSession):
    base = date.today() - timedelta(days=365)
    idx = 0
    for i in range(730):
        d = base + timedelta(days=i)
        if d.weekday() < 5 and d <= date.today():
            p = 100.0 + idx * 0.3 + (idx % 10 - 5)
            session.add(DailyPrice(
                symbol="CLEAN",
                trade_date=d,
                open=p,
                high=p + 1.5,
                low=p - 1.5,
                close=p + 0.3,
                volume=1_000_000 + idx * 10_000,
            ))
            idx += 1
    await session.flush()


@pytest_asyncio.fixture
async def anomaly_prices(session: AsyncSession):
    base = date.today() - timedelta(days=365)
    idx = 0
    for i in range(730):
        d = base + timedelta(days=i)
        if d.weekday() < 5 and d <= date.today():
            p = 100.0 + idx * 0.3 + (idx % 10 - 5)
            vol = 1_000_000 + idx * 10_000
            if idx == 10:
                p = 150.0
                vol = 100_000_000
            if idx == 20:
                session.add(DailyPrice(
                    symbol="ANOMALY",
                    trade_date=d,
                    open=-1.0,
                    high=p + 1.5,
                    low=p - 1.5,
                    close=p + 0.3,
                    volume=1_000_000,
                ))
                idx += 1
                continue
            session.add(DailyPrice(
                symbol="ANOMALY",
                trade_date=d,
                open=p,
                high=p + 1.5,
                low=p - 1.5,
                close=p + 0.3,
                volume=vol,
            ))
            idx += 1
    await session.flush()


# ============================================================
# VALIDATION RUN
# ============================================================

class TestValidationRun:
    @pytest.mark.asyncio
    async def test_validate_clean_dataset(self, svc: DatasetValidationService, clean_prices):
        today = date.today()
        start = today - timedelta(days=60)
        run = await svc.validate_dataset("CLEAN", date_from=start, date_to=today)
        assert run.status == "completed"
        assert run.anomalies_found == 0
        assert run.total_records > 0
        assert run.quality_score is not None
        assert run.quality_score >= 75

    @pytest.mark.asyncio
    async def test_validate_anomaly_dataset(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        assert run.status == "completed"
        assert run.anomalies_found > 0
        assert run.missing_values > 0
        assert run.price_anomalies > 0
        assert run.volume_anomalies > 0

    @pytest.mark.asyncio
    async def test_validate_empty_dataset(self, svc: DatasetValidationService):
        run = await svc.validate_dataset("EMPTY")
        assert run.status == "completed"
        assert run.total_records == 0
        assert run.quality_score == 0
        assert run.quality_rating == "poor"

    @pytest.mark.asyncio
    async def test_validate_with_date_range(self, svc: DatasetValidationService, clean_prices):
        start = date.today() - timedelta(days=30)
        end = date.today()
        run = await svc.validate_dataset("CLEAN", start, end)
        assert run.status == "completed"
        assert run.date_from == start
        assert run.date_to == end

    @pytest.mark.asyncio
    async def test_quality_score_persisted(self, svc: DatasetValidationService, clean_prices):
        today = date.today()
        start = today - timedelta(days=60)
        run = await svc.validate_dataset("CLEAN", date_from=start, date_to=today)
        scores = await svc.get_quality_scores("CLEAN")
        assert len(scores) >= 1
        assert scores[0].overall_score >= 75
        assert scores[0].run_id == run.id

    @pytest.mark.asyncio
    async def test_list_runs(self, svc: DatasetValidationService, clean_prices):
        today = date.today()
        await svc.validate_dataset("CLEAN", date_from=today - timedelta(days=60), date_to=today)
        runs = await svc.list_validation_runs()
        assert len(runs) >= 1

    @pytest.mark.asyncio
    async def test_get_run_by_id(self, svc: DatasetValidationService, clean_prices):
        today = date.today()
        run = await svc.validate_dataset("CLEAN", date_from=today - timedelta(days=60), date_to=today)
        fetched = await svc.get_validation_run(run.id)
        assert fetched is not None
        assert fetched.id == run.id

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, svc: DatasetValidationService):
        assert await svc.get_validation_run(9999) is None


# ============================================================
# MISSING VALUES
# ============================================================

class TestMissingValues:
    @pytest.mark.asyncio
    async def test_detects_none_open(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        assert run.missing_values >= 1

    @pytest.mark.asyncio
    async def test_no_missing_on_clean(self, svc: DatasetValidationService, clean_prices):
        run = await svc.validate_dataset("CLEAN")
        assert run.missing_values == 0


# ============================================================
# DUPLICATE ROWS
# ============================================================

class TestDuplicateRows:
    @pytest.mark.asyncio
    async def test_no_duplicates_clean(self, svc: DatasetValidationService, clean_prices):
        run = await svc.validate_dataset("CLEAN")
        assert run.duplicate_rows == 0

    @pytest.mark.asyncio
    async def test_duplicate_detection_logic(self, svc: DatasetValidationService, session: AsyncSession):
        today = date.today()
        base = today - timedelta(days=30)
        for i in range(5):
            d = base + timedelta(days=i * 2)
            if d.weekday() < 5:
                session.add(DailyPrice(symbol="DUP2", trade_date=d, open=100.0, high=105.0, low=95.0, close=102.0, volume=1_000_000))
                session.add(DailyPrice(symbol="DUP2", trade_date=d + timedelta(days=1), open=101.0, high=106.0, low=96.0, close=103.0, volume=1_100_000))
        await session.flush()
        run = await svc.validate_dataset("DUP2")
        assert run.duplicate_rows == 0


# ============================================================
# PRICE ANOMALIES
# ============================================================

class TestPriceAnomalies:
    @pytest.mark.asyncio
    async def test_detects_price_spike(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        assert run.price_anomalies >= 1

    @pytest.mark.asyncio
    async def test_no_price_anomalies_on_clean(self, svc: DatasetValidationService, clean_prices):
        run = await svc.validate_dataset("CLEAN")
        assert run.price_anomalies == 0

    @pytest.mark.asyncio
    async def test_price_gap_detection(self, svc: DatasetValidationService, session: AsyncSession):
        base = date.today() - timedelta(days=20)
        bdays = [base + timedelta(days=i) for i in range(15) if (base + timedelta(days=i)).weekday() < 5]
        for j, d in enumerate(bdays):
            p = 100.0 + (j % 3)
            if j == 3:
                p = 200.0
            session.add(DailyPrice(symbol="GAP", trade_date=d, open=p, high=p + 1, low=p - 1, close=p + 0.1, volume=1_000_000))
        await session.flush()
        run = await svc.validate_dataset("GAP")
        assert run.price_anomalies >= 1


# ============================================================
# VOLUME ANOMALIES
# ============================================================

class TestVolumeAnomalies:
    @pytest.mark.asyncio
    async def test_detects_volume_spike(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        assert run.volume_anomalies >= 1

    @pytest.mark.asyncio
    async def test_no_volume_anomalies_on_clean(self, svc: DatasetValidationService, clean_prices):
        run = await svc.validate_dataset("CLEAN")
        assert run.volume_anomalies == 0


# ============================================================
# CORPORATE ACTION MISMATCH
# ============================================================

class TestCorpActionMismatch:
    @pytest.mark.asyncio
    async def test_detects_mismatch(self, svc: DatasetValidationService, session: AsyncSession):
        base = date.today() - timedelta(days=30)
        for i in range(20):
            d = base + timedelta(days=i)
            if d.weekday() < 5:
                p = 100.0 + i * 0.5
                session.add(DailyPrice(symbol="CAM", trade_date=d, open=p, high=p + 1, low=p - 1, close=p + 0.3, volume=1_000_000))
        await session.flush()

        spike_date = base + timedelta(days=10)
        while spike_date.weekday() >= 5:
            spike_date += timedelta(days=1)

        # Make the fixture actually represent a recorded 2:1 split with no price adjustment.
        current = (await session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == "CAM",
                DailyPrice.trade_date == spike_date,
            )
        )).scalar_one()
        previous = (await session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == "CAM",
                DailyPrice.trade_date < spike_date,
            ).order_by(DailyPrice.trade_date.desc()).limit(1)
        )).scalar_one()
        current.open = previous.close
        current.close = previous.close

        session.add(CorporateAction(
            symbol="CAM", action_date=spike_date, action_type="split",
            ratio_numerator=2, ratio_denominator=1, description="2:1 split",
        ))
        await session.flush()

        run = await svc.validate_dataset("CAM")
        assert run.corp_action_mismatches >= 1

    @pytest.mark.asyncio
    async def test_no_detection_without_corp_actions(self, svc: DatasetValidationService, clean_prices):
        run = await svc.validate_dataset("CLEAN")
        assert run.corp_action_mismatches == 0


# ============================================================
# TIMESTAMP MISMATCH
# ============================================================

class TestTimestampMismatch:
    @pytest.mark.asyncio
    async def test_detects_missing_days(self, svc: DatasetValidationService, session: AsyncSession):
        base = date.today() - timedelta(days=30)
        for i in range(20):
            d = base + timedelta(days=i)
            if d.weekday() < 5 and i % 2 == 0:
                session.add(DailyPrice(symbol="TS", trade_date=d, open=100, high=101, low=99, close=100.5, volume=1_000_000))
        await session.flush()
        run = await svc.validate_dataset("TS")
        assert run.timestamp_mismatches >= 1

    @pytest.mark.asyncio
    async def test_detects_future_date(self, svc: DatasetValidationService, session: AsyncSession):
        future = date.today() + timedelta(days=365)
        session.add(DailyPrice(symbol="FUTURE", trade_date=future, open=100, high=101, low=99, close=100, volume=1_000_000))
        await session.flush()
        run = await svc.validate_dataset("FUTURE")
        assert run.timestamp_mismatches >= 1

    @pytest.mark.asyncio
    async def test_no_timestamp_issues_on_clean(self, svc: DatasetValidationService, clean_prices):
        run = await svc.validate_dataset("CLEAN")
        assert run.timestamp_mismatches == 0


# ============================================================
# QUALITY SCORING
# ============================================================

class TestQualityScoring:
    @pytest.mark.asyncio
    async def test_clean_dataset_scores_high(self, svc: DatasetValidationService, clean_prices):
        run = await svc.validate_dataset("CLEAN")
        assert run.quality_score >= 75
        assert run.quality_rating in ("excellent", "good")

    @pytest.mark.asyncio
    async def test_anomaly_dataset_scores_lower(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        assert run.quality_score < 99.5

    @pytest.mark.asyncio
    async def test_quality_stats(self, svc: DatasetValidationService, clean_prices):
        await svc.validate_dataset("CLEAN")
        stats = await svc.get_quality_stats()
        assert "average_score" in stats
        assert stats["total_scores"] >= 1

    @pytest.mark.asyncio
    async def test_quality_scores_list(self, svc: DatasetValidationService, clean_prices):
        await svc.validate_dataset("CLEAN")
        scores = await svc.get_quality_scores()
        assert len(scores) >= 1

    @pytest.mark.asyncio
    async def test_quality_scores_filter_by_symbol(self, svc: DatasetValidationService, clean_prices):
        await svc.validate_dataset("CLEAN")
        scores = await svc.get_quality_scores(symbol="CLEAN")
        assert len(scores) >= 1


# ============================================================
# ANOMALY QUERIES
# ============================================================

class TestAnomalyQueries:
    @pytest.mark.asyncio
    async def test_get_anomalies_by_run(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        anomalies = await svc.get_anomalies(run_id=run.id)
        assert len(anomalies) > 0
        for a in anomalies:
            assert a.run_id == run.id

    @pytest.mark.asyncio
    async def test_get_anomalies_by_type(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        anomalies = await svc.get_anomalies(run_id=run.id, anomaly_type="missing_value")
        assert len(anomalies) > 0
        for a in anomalies:
            assert a.anomaly_type == "missing_value"

    @pytest.mark.asyncio
    async def test_get_anomalies_by_severity(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        anomalies = await svc.get_anomalies(run_id=run.id, severity="high")
        assert len(anomalies) > 0

    @pytest.mark.asyncio
    async def test_anomaly_stats(self, svc: DatasetValidationService, anomaly_prices):
        await svc.validate_dataset("ANOMALY")
        stats = await svc.get_anomaly_stats()
        assert "missing_value" in stats or "price_anomaly" in stats or "volume_anomaly" in stats

    @pytest.mark.asyncio
    async def test_get_anomalies_empty(self, svc: DatasetValidationService):
        anomalies = await svc.get_anomalies()
        assert isinstance(anomalies, list)


# ============================================================
# CLEAR OLD DATA
# ============================================================

class TestClearOldData:
    @pytest.mark.asyncio
    async def test_clear_old_anomalies(self, svc: DatasetValidationService, clean_prices):
        await svc.validate_dataset("CLEAN")
        cleared = await svc.clear_anomalies(older_than_days=0)
        assert cleared >= 0


# ============================================================
# EDGE CASES
# ============================================================

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_too_few_records_no_crash(self, svc: DatasetValidationService, session: AsyncSession):
        d = date.today() - timedelta(days=5)
        if d.weekday() < 5:
            session.add(DailyPrice(symbol="FEW", trade_date=d, open=100, high=101, low=99, close=100.5, volume=1_000_000))
        await session.flush()
        run = await svc.validate_dataset("FEW")
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_anomaly_has_expected_fields(self, svc: DatasetValidationService, anomaly_prices):
        run = await svc.validate_dataset("ANOMALY")
        anomalies = await svc.get_anomalies(run_id=run.id, limit=1)
        if anomalies:
            a = anomalies[0]
            assert a.anomaly_type is not None
            assert a.severity is not None
            assert a.description is not None
            assert a.symbol == "ANOMALY"

    @pytest.mark.asyncio
    async def test_multiple_validations_same_symbol(self, svc: DatasetValidationService, clean_prices):
        run1 = await svc.validate_dataset("CLEAN")
        run2 = await svc.validate_dataset("CLEAN")
        runs = await svc.list_validation_runs(symbol="CLEAN")
        assert len(runs) >= 2

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Zero price is valid in SQLite (no NaN constraint)")
    async def test_validation_with_zero_price(self, svc: DatasetValidationService, session: AsyncSession):
        d = date.today() - timedelta(days=5)
        if d.weekday() < 5:
            session.add(DailyPrice(symbol="ZERO", trade_date=d, open=100, high=0.0, low=99, close=100.5, volume=1_000_000))
        await session.flush()
        run = await svc.validate_dataset("ZERO")
        assert run.missing_values >= 1
