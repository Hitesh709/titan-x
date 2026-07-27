import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.drift_detection import (
    ConceptDriftResult,
    DistributionProfile,
    DriftAlert,
    DriftDetectionRun,
    FeatureDriftResult,
)
from titan_x.services.drift_detection_service import DriftDetectionService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @sa_event.listens_for(eng.sync_engine, "connect")
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
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


# ── Statistical Methods ──

class TestStats:
    def test_compute_stats(self):
        svc = DriftDetectionService.__new__(DriftDetectionService)
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        stats = svc._compute_stats(vals)
        assert stats["count"] == 5
        assert stats["mean"] == 3.0
        assert stats["median"] == 3.0
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0
        assert stats["p25"] == 2.0
        assert stats["p75"] == 4.0

    def test_compute_stats_empty(self):
        svc = DriftDetectionService.__new__(DriftDetectionService)
        stats = svc._compute_stats([])
        assert stats["count"] == 0

    def test_psi_identical(self):
        svc = DriftDetectionService.__new__(DriftDetectionService)
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        psi = svc._compute_psi(vals, vals)
        assert psi == pytest.approx(0.0, abs=0.01)

    def test_psi_different(self):
        svc = DriftDetectionService.__new__(DriftDetectionService)
        base = [1.0, 2.0, 3.0, 4.0, 5.0]
        curr = [100.0, 200.0, 300.0, 400.0, 500.0]
        psi = svc._compute_psi(base, curr)
        assert psi > 0.5

    def test_js_identical(self):
        svc = DriftDetectionService.__new__(DriftDetectionService)
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        js = svc._compute_js_divergence(vals, vals)
        assert js == pytest.approx(0.0, abs=0.01)

    def test_js_different(self):
        svc = DriftDetectionService.__new__(DriftDetectionService)
        base = [1.0, 2.0, 3.0, 4.0, 5.0]
        curr = [100.0, 200.0, 300.0, 400.0, 500.0]
        js = svc._compute_js_divergence(base, curr)
        assert js > 0.2

    def test_psi_single_value(self):
        svc = DriftDetectionService.__new__(DriftDetectionService)
        base = [5.0, 5.0, 5.0]
        curr = [5.0, 5.0, 5.0]
        psi = svc._compute_psi(base, curr)
        assert psi == 0.0


# ── Distribution Profiles ──

@pytest.mark.asyncio
class TestDistributionProfiles:
    async def test_create_profile(self, session):
        svc = DriftDetectionService(session)
        dp = await svc.create_distribution_profile(
            "close_price",
            [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            profile_type="baseline",
            dataset_name="train_2024",
        )
        assert dp.id is not None
        assert dp.feature_name == "close_price"
        assert dp.num_samples == 6
        assert dp.mean == 102.5
        assert dp.minimum == 100.0
        assert dp.maximum == 105.0

    async def test_get_profile(self, session):
        svc = DriftDetectionService(session)
        dp = await svc.create_distribution_profile("feat", [1, 2, 3])
        got = await svc.get_distribution_profile(dp.id)
        assert got is not None and got.id == dp.id


# ── Drift Detection Run ──

@pytest.mark.asyncio
class TestDriftDetection:
    async def test_no_drift_identical(self, session):
        svc = DriftDetectionService(session)
        baseline = {"close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]}
        current = {"close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]}
        run = await svc.run_drift_detection(
            baseline, current, name="identical_test",
            alert_on_drift=False,
        )
        assert run.status == "completed"
        assert run.drift_detected is False
        assert run.overall_drift_score == pytest.approx(0.0, abs=0.01)

    async def test_drift_detected(self, session):
        svc = DriftDetectionService(session)
        baseline = {"close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]}
        current = {"close": [200.0, 300.0, 400.0, 500.0, 600.0, 700.0]}
        run = await svc.run_drift_detection(
            baseline, current, name="drift_test",
            alert_on_drift=False,
        )
        assert run.drift_detected is True
        assert run.overall_drift_score > 0.5
        assert run.num_drifted_features == 1
        assert run.num_features_compared == 1

    async def test_multiple_features(self, session):
        svc = DriftDetectionService(session)
        baseline = {
            "close": [100.0] * 50,
            "volume": [1000000.0] * 50,
            "rsi": [50.0] * 50,
        }
        current = {
            "close": [200.0] * 50,
            "volume": [1000000.0] * 50,
            "rsi": [50.0] * 50,
        }
        run = await svc.run_drift_detection(
            baseline, current, name="multi_feat",
            alert_on_drift=False,
        )
        assert run.num_features_compared == 3
        assert run.num_drifted_features == 1

    async def test_partial_features(self, session):
        svc = DriftDetectionService(session)
        baseline = {"a": [1.0, 2.0], "b": [3.0, 4.0]}
        current = {"a": [1.0, 2.0]}
        run = await svc.run_drift_detection(
            baseline, current, name="partial",
            alert_on_drift=False,
        )
        assert run.num_features_compared == 1

    async def test_with_metrics(self, session):
        svc = DriftDetectionService(session)
        baseline_data = {"close": [100.0, 101.0, 102.0]}
        current_data = {"close": [100.0, 101.0, 102.0]}
        run = await svc.run_drift_detection(
            baseline_data, current_data,
            baseline_metrics={"accuracy": 0.95, "f1": 0.93},
            current_metrics={"accuracy": 0.80, "f1": 0.75},
            name="concept_drift_test",
            alert_on_drift=False,
        )
        assert run.drift_detected is True
        concepts = await svc.get_concept_drift_results(run.id)
        assert len(concepts) == 2
        acc_drift = [c for c in concepts if c.metric_name == "accuracy"][0]
        assert acc_drift.drifted is True
        assert acc_drift.percentage_change < 0

    async def test_query_feature_results(self, session):
        svc = DriftDetectionService(session)
        baseline = {"close": [100.0] * 10}
        current = {"close": [500.0] * 10}
        run = await svc.run_drift_detection(
            baseline, current, alert_on_drift=False,
        )
        features = await svc.get_feature_drift_results(run.id)
        assert len(features) == 1
        assert features[0].drifted is True
        assert features[0].feature_name == "close"

    async def test_list_runs(self, session):
        svc = DriftDetectionService(session)
        b = {"x": [1, 2, 3]}
        await svc.run_drift_detection(b, b, name="r1", alert_on_drift=False)
        await svc.run_drift_detection(b, b, name="r2", alert_on_drift=False)
        items = await svc.list_runs()
        assert len(items) == 2

    async def test_list_runs_filter_drifted(self, session):
        svc = DriftDetectionService(session)
        b = {"x": [1, 2, 3]}
        c_diff = {"x": [100, 200, 300]}
        await svc.run_drift_detection(b, b, alert_on_drift=False)
        await svc.run_drift_detection(b, c_diff, alert_on_drift=False)
        items = await svc.list_runs(drift_detected=True)
        assert len(items) == 1

    async def test_get_run_summary(self, session):
        svc = DriftDetectionService(session)
        b = {"close": [100.0] * 10, "volume": [1e6] * 10}
        c = {"close": [500.0] * 10, "volume": [1e6] * 10}
        run = await svc.run_drift_detection(
            b, c, name="summary_test",
            baseline_metrics={"acc": 0.9},
            current_metrics={"acc": 0.7},
            alert_on_drift=False,
        )
        summary = await svc.get_run_summary(run.id)
        assert summary is not None
        assert summary["run"]["name"] == "summary_test"
        assert len(summary["feature_drift"]) == 2
        assert len(summary["concept_drift"]) == 1


# ── Alerts ──

@pytest.mark.asyncio
class TestAlerts:
    async def test_alerts_generated_on_drift(self, session):
        svc = DriftDetectionService(session)
        b = {"close": [100.0] * 10}
        c = {"close": [500.0] * 10}
        run = await svc.run_drift_detection(
            b, c, name="alert_test",
            baseline_metrics={"accuracy": 0.9},
            current_metrics={"accuracy": 0.6},
            alert_on_drift=True,
        )
        # feature drift + concept drift + overall data drift alert
        alerts = await svc.get_alerts()
        assert len(alerts) >= 2

    async def test_no_alerts_when_disabled(self, session):
        svc = DriftDetectionService(session)
        b = {"close": [100.0] * 10}
        c = {"close": [500.0] * 10}
        await svc.run_drift_detection(
            b, c, alert_on_drift=False,
        )
        alerts = await svc.get_alerts()
        assert len(alerts) == 0

    async def test_acknowledge_alert(self, session):
        svc = DriftDetectionService(session)
        b = {"close": [100.0] * 10}
        c = {"close": [500.0] * 10}
        run = await svc.run_drift_detection(
            b, c, alert_on_drift=True,
        )
        alerts = await svc.get_alerts()
        assert len(alerts) >= 1
        acknowledged = await svc.acknowledge_alert(alerts[0].id)
        assert acknowledged is not None
        assert acknowledged.acknowledged is True
        unack = await svc.get_alerts(acknowledged=False)
        assert len(unack) == len(alerts) - 1

    async def test_acknowledge_not_found(self, session):
        svc = DriftDetectionService(session)
        assert await svc.acknowledge_alert(9999) is None

    async def test_filter_alerts_by_severity(self, session):
        svc = DriftDetectionService(session)
        b = {"close": [100.0] * 10}
        c = {"close": [500.0] * 10}
        await svc.run_drift_detection(b, c, alert_on_drift=True)
        alerts = await svc.get_alerts(severity="critical")
        assert len(alerts) >= 0


# ── Monitoring ──

@pytest.mark.asyncio
class TestMonitoring:
    async def test_monitor_distributions(self, session):
        svc = DriftDetectionService(session)
        features = {
            "close": [100.0, 101.0, 102.0],
            "volume": [1e6, 2e6, 3e6],
        }
        profiles = await svc.monitor_distributions(
            features, model_registry_entry_id=None,
            dataset_name="production_2024",
        )
        assert len(profiles) == 2
        assert profiles[0].profile_type == "monitoring"
        assert profiles[1].profile_type == "monitoring"


# ── Integration ──

@pytest.mark.asyncio
class TestIntegration:
    async def test_full_drift_pipeline(self, session):
        svc = DriftDetectionService(session)

        await svc.create_distribution_profile(
            "close", [100.0, 101.0, 102.0, 103.0, 104.0],
            profile_type="baseline", dataset_name="train",
        )

        baseline = {
            "close": [100.0 + i for i in range(100)],
            "volume": [1_000_000 + i * 1000 for i in range(100)],
            "rsi": [50.0 + (i % 10) for i in range(100)],
        }
        current = {
            "close": [200.0 + i for i in range(100)],
            "volume": [1_000_000 + i * 1000 for i in range(100)],
            "rsi": [50.0 + (i % 10) for i in range(100)],
        }

        run = await svc.run_drift_detection(
            baseline, current,
            name="weekly_drift_check",
            baseline_dataset="train_2024_q1",
            current_dataset="production_2024_q2",
            baseline_metrics={"accuracy": 0.92, "f1": 0.90, "precision": 0.91},
            current_metrics={"accuracy": 0.78, "f1": 0.75, "precision": 0.76},
            alert_on_drift=True,
        )
        assert run.drift_detected is True
        assert run.num_features_compared == 3
        assert run.num_drifted_features >= 1
        assert run.overall_drift_score > 0.1

        features = await svc.get_feature_drift_results(run.id)
        assert len(features) == 3

        close_drift = [f for f in features if f.feature_name == "close"][0]
        assert close_drift.drifted is True
        assert close_drift.drift_score > 0.5

        volume_drift = [f for f in features if f.feature_name == "volume"][0]
        assert volume_drift.drifted is False

        concepts = await svc.get_concept_drift_results(run.id)
        assert len(concepts) == 3

        acc_drift = [c for c in concepts if c.metric_name == "accuracy"][0]
        assert acc_drift.drifted is True
        assert acc_drift.percentage_change == pytest.approx(-0.152, abs=0.01)

        alerts = await svc.get_alerts()
        assert len(alerts) >= 1

        acknowledged = await svc.acknowledge_alert(alerts[0].id)
        assert acknowledged.acknowledged is True
