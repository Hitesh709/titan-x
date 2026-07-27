import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.model_evaluation import ModelEvaluation, ModelEvaluationMetric
from titan_x.services.model_evaluation_service import ModelEvaluationService

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


# ── Metric Computation (synchronous) ──

class TestComputeMetrics:
    def test_perfect_prediction(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        y_true = [1, 0, 1, 0, 1]
        y_pred = [1, 0, 1, 0, 1]
        y_prob = [0.9, 0.1, 0.95, 0.05, 0.99]
        result = svc.compute_metrics(y_true, y_pred, y_prob=y_prob)
        assert result.accuracy == 1.0
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.roc_auc == 1.0

    def test_all_wrong(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        y_true = [1, 0, 1, 0]
        y_pred = [0, 1, 0, 1]
        y_prob = [0.1, 0.9, 0.1, 0.9]
        result = svc.compute_metrics(y_true, y_pred, y_prob=y_prob)
        assert result.accuracy == 0.0
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0
        assert result.roc_auc == 0.0

    def test_mixed_results(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        y_true = [1, 1, 0, 0, 1, 0, 1, 0]
        y_pred = [1, 1, 0, 0, 0, 1, 1, 0]
        y_prob = [0.9, 0.85, 0.2, 0.1, 0.4, 0.6, 0.95, 0.3]
        result = svc.compute_metrics(y_true, y_pred, y_prob=y_prob)
        assert result.accuracy == 0.75
        assert result.precision == 0.75
        assert result.recall == 0.75
        assert result.f1 == 0.75
        assert 0.5 < result.roc_auc < 1.0

    def test_empty_input(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        with pytest.raises(ValueError):
            svc.compute_metrics([], [])

    def test_profitability(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        returns = [0.1, 0.2, -0.05, 0.15, -0.02]
        y_true = [1, 1, 1, 1, 1]
        y_pred = [1, 1, 1, 1, 1]
        result = svc.compute_metrics(y_true, y_pred, returns=returns)
        assert result.profitability == pytest.approx(0.076, abs=0.001)

    def test_win_rate(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        returns = [0.1, -0.05, 0.2, -0.1, 0.05, 0.15]
        y_true = [1] * 6
        y_pred = [1] * 6
        result = svc.compute_metrics(y_true, y_pred, returns=returns)
        assert result.win_rate == pytest.approx(4 / 6, abs=0.001)

    def test_max_drawdown(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        returns = [1.0, 2.0, -0.5, 0.5, -1.0]
        y_true = [1] * 5
        y_pred = [1] * 5
        result = svc.compute_metrics(y_true, y_pred, returns=returns)
        assert result.max_drawdown > 0.0

    def test_custom_threshold(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        y_true = [1, 0, 1, 0]
        y_pred = [0.6, 0.4, 0.7, 0.3]
        result_low = svc.compute_metrics(y_true, y_pred, threshold=0.5)
        result_high = svc.compute_metrics(y_true, y_pred, threshold=0.8)
        assert result_low.accuracy != result_high.accuracy

    def test_roc_auc_random(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        y_true = [1, 0, 1, 0, 1, 0, 1, 0]
        y_prob = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        result = svc.compute_metrics(y_true, y_pred=y_true, y_prob=y_prob)
        assert result.roc_auc == 0.5

    def test_roc_auc_single_class(self):
        svc = ModelEvaluationService.__new__(ModelEvaluationService)
        y_true = [1, 1, 1]
        y_pred = [1, 1, 1]
        y_prob = [0.9, 0.8, 0.95]
        result = svc.compute_metrics(y_true, y_pred, y_prob=y_prob)
        assert result.roc_auc == 0.0


# ── DB Integration (async) ──

@pytest.mark.asyncio
class TestEvaluationDB:
    async def test_run_evaluation(self, session):
        svc = ModelEvaluationService(session)
        ev = await svc.run_evaluation(
            y_true=[1, 0, 1, 0],
            y_pred=[1, 0, 1, 0],
            y_prob=[0.9, 0.1, 0.95, 0.05],
            returns=[0.1, -0.05, 0.2, 0.15],
            name="perfect_test",
            dataset_name="test_set_v1",
            notes="All correct",
        )
        assert ev.id is not None
        assert ev.status == "completed"
        assert ev.num_samples == 4
        assert ev.name == "perfect_test"
        assert ev.evaluated_at is not None

        metrics = await svc.get_evaluation_metrics(ev.id)
        metric_map = {m.metric_name: m.metric_value for m in metrics}
        assert metric_map["accuracy"] == 1.0
        assert metric_map["precision"] == 1.0
        assert metric_map["recall"] == 1.0
        assert metric_map["f1"] == 1.0
        assert metric_map["roc_auc"] == 1.0
        assert len(metrics) == 8

    async def test_run_evaluation_no_proba(self, session):
        svc = ModelEvaluationService(session)
        ev = await svc.run_evaluation(
            y_true=[1, 0, 1], y_pred=[1, 0, 1],
            name="no_proba",
        )
        metrics = await svc.get_evaluation_metrics(ev.id)
        metric_map = {m.metric_name: m.metric_value for m in metrics}
        assert metric_map["accuracy"] == 1.0
        assert metric_map["roc_auc"] == 0.0

    async def test_get_evaluation(self, session):
        svc = ModelEvaluationService(session)
        ev = await svc.run_evaluation(y_true=[1, 0], y_pred=[1, 0], name="get_test")
        got = await svc.get_evaluation(ev.id)
        assert got is not None and got.id == ev.id

    async def test_get_evaluation_not_found(self, session):
        svc = ModelEvaluationService(session)
        assert await svc.get_evaluation(9999) is None

    async def test_list_evaluations(self, session):
        svc = ModelEvaluationService(session)
        await svc.run_evaluation(y_true=[1, 0], y_pred=[1, 0], name="a")
        await svc.run_evaluation(y_true=[1, 0], y_pred=[1, 0], name="b")
        items = await svc.list_evaluations()
        assert len(items) == 2

    async def test_get_metric_history(self, session):
        svc = ModelEvaluationService(session)
        for _ in range(3):
            await svc.run_evaluation(
                y_true=[1, 0, 1, 0], y_pred=[1, 0, 1, 0],
            )
        history = await svc.get_metric_history("accuracy")
        assert len(history) == 3
        for entry in history:
            assert entry["metric_value"] == 1.0

    async def test_compare_evaluations(self, session):
        svc = ModelEvaluationService(session)
        e1 = await svc.run_evaluation(
            y_true=[1, 0, 1, 0], y_pred=[1, 0, 1, 0],
            name="perfect",
        )
        e2 = await svc.run_evaluation(
            y_true=[1, 0, 1, 0], y_pred=[0, 1, 0, 1],
            name="worst",
        )
        result = await svc.compare_evaluations([e1.id, e2.id])
        assert len(result["evaluations"]) == 2
        assert result["metrics_comparison"]["accuracy"]["best_evaluation_id"] == e1.id
        assert result["metrics_comparison"]["accuracy"]["best_value"] == 1.0


# ── Integration ──

@pytest.mark.asyncio
class TestIntegration:
    async def test_full_evaluation_lifecycle(self, session):
        svc = ModelEvaluationService(session)

        y_true = [1, 1, 0, 0, 1, 0, 1, 1, 0, 0]
        y_pred = [1, 1, 0, 1, 1, 0, 1, 0, 0, 0]
        y_prob = [0.9, 0.85, 0.1, 0.6, 0.95, 0.05, 0.88, 0.3, 0.2, 0.15]
        trades = [0.1, 0.2, 0.05, -0.03, 0.15, 0.01, -0.05, 0.08, 0.02, -0.01]

        ev = await svc.run_evaluation(
            y_true=y_true, y_pred=y_pred, y_prob=y_prob,
            returns=trades,
            name="xgboost_v2_test",
            dataset_name="test_2024_q1",
            notes="First evaluation after retraining",
        )
        assert ev.num_samples == 10
        assert ev.status == "completed"

        metrics = await svc.get_evaluation_metrics(ev.id)
        metric_map = {m.metric_name: m.metric_value for m in metrics}
        assert "accuracy" in metric_map
        assert "precision" in metric_map
        assert "recall" in metric_map
        assert "f1" in metric_map
        assert "roc_auc" in metric_map
        assert "profitability" in metric_map
        assert "win_rate" in metric_map
        assert "max_drawdown" in metric_map

        history = await svc.get_metric_history("accuracy")
        assert len(history) >= 1

        comparison = await svc.compare_evaluations([ev.id])
        assert len(comparison["evaluations"]) == 1

    async def test_multiple_evaluations_comparison(self, session):
        svc = ModelEvaluationService(session)
        configs = [
            (8, "v1"),
            (10, "v2"),
            (5, "v3"),
        ]
        ids = []
        for correct, name in configs:
            y_true = [1] * 10
            y_pred = [1] * correct + [0] * (10 - correct)
            ev = await svc.run_evaluation(
                y_true=y_true, y_pred=y_pred,
                name=name, dataset_name="test_set",
            )
            ids.append(ev.id)

        result = await svc.compare_evaluations(ids)
        best_id = result["metrics_comparison"]["accuracy"]["best_evaluation_id"]
        best = await svc.get_evaluation(best_id)
        assert best.name == "v2"
