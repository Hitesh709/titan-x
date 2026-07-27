import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.experiment_manager import (
    Experiment,
    ExperimentArtifact,
    ExperimentChart,
    ExperimentMetric,
    ExperimentParameter,
    ExperimentTag,
)
from titan_x.services.experiment_manager_service import ExperimentManagerService

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


pytestmark = pytest.mark.asyncio


# ── Experiments ──

class TestExperiments:
    async def test_create_experiment(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment(
            "xgboost_tuning_v1",
            description="First XGBoost hyperparameter tuning",
            metadata={"framework": "xgboost", "version": "2.0"},
            tags={"dataset": "stock_prices", "type": "classification"},
        )
        assert exp.id is not None
        assert exp.experiment_id is not None
        assert exp.name == "xgboost_tuning_v1"
        assert exp.status == "running"
        assert exp.started_at is not None

    async def test_get_experiment(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("test")
        got = await svc.get_experiment(exp.id)
        assert got is not None and got.id == exp.id

    async def test_get_experiment_by_uuid(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("uuid_test", experiment_id="abc-123")
        got = await svc.get_experiment_by_uuid("abc-123")
        assert got is not None and got.id == exp.id

    async def test_get_experiment_not_found(self, session):
        svc = ExperimentManagerService(session)
        assert await svc.get_experiment(9999) is None

    async def test_list_experiments(self, session):
        svc = ExperimentManagerService(session)
        await svc.create_experiment("a")
        await svc.create_experiment("b")
        items = await svc.list_experiments()
        assert len(items) == 2

    async def test_list_experiments_filter_status(self, session):
        svc = ExperimentManagerService(session)
        e1 = await svc.create_experiment("running_exp")
        e2 = await svc.create_experiment("completed_exp")
        await svc.update_experiment_status(e2.id, "completed")
        items = await svc.list_experiments(status="completed")
        assert len(items) == 1
        assert items[0].id == e2.id

    async def test_update_status(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("status_test")
        updated = await svc.update_experiment_status(exp.id, "completed")
        assert updated is not None
        assert updated.status == "completed"
        assert updated.completed_at is not None
        assert updated.duration_seconds is not None

    async def test_delete_experiment(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("to_delete")
        ok = await svc.delete_experiment(exp.id)
        assert ok is True
        assert await svc.get_experiment(exp.id) is None

    async def test_delete_experiment_not_found(self, session):
        svc = ExperimentManagerService(session)
        assert await svc.delete_experiment(9999) is False


# ── Parameters ──

class TestParameters:
    async def test_log_parameter(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("param_test")
        ep = await svc.log_parameter(exp.id, "learning_rate", 0.01)
        assert ep.id is not None
        assert ep.key == "learning_rate"
        assert ep.value == "0.01"
        assert ep.param_type == "float"

    async def test_log_parameters_batch(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("batch_params")
        params = {"lr": 0.001, "max_depth": 6, "n_estimators": 100}
        items = await svc.log_parameters(exp.id, params)
        assert len(items) == 3

    async def test_get_parameters(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("get_params")
        await svc.log_parameter(exp.id, "a", 1)
        await svc.log_parameter(exp.id, "b", 2)
        items = await svc.get_parameters(exp.id)
        assert len(items) == 2


# ── Metrics ──

class TestMetrics:
    async def test_log_metric(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("metric_test")
        em = await svc.log_metric(exp.id, "accuracy", 0.95, step=1, epoch=1)
        assert em.id is not None
        assert em.key == "accuracy"
        assert em.value == 0.95
        assert em.step == 1

    async def test_log_metrics_batch(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("batch_metrics")
        items = await svc.log_metrics(exp.id, {"loss": 0.25, "acc": 0.9}, step=5)
        assert len(items) == 2

    async def test_get_metrics(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("get_metrics")
        await svc.log_metric(exp.id, "loss", 0.5, step=1)
        await svc.log_metric(exp.id, "loss", 0.3, step=2)
        await svc.log_metric(exp.id, "acc", 0.9, step=1)
        items = await svc.get_metrics(exp.id)
        assert len(items) == 3

    async def test_get_metrics_by_key(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("filter_metrics")
        await svc.log_metric(exp.id, "loss", 0.5)
        await svc.log_metric(exp.id, "loss", 0.3)
        await svc.log_metric(exp.id, "acc", 0.9)
        items = await svc.get_metrics(exp.id, key="loss")
        assert len(items) == 2

    async def test_get_metric_history(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("history")
        for step in range(1, 6):
            await svc.log_metric(exp.id, "loss", 1.0 / step, step=step)
        history = await svc.get_metric_history(exp.id, "loss")
        assert len(history) == 5
        assert history[0].step == 1


# ── Artifacts ──

class TestArtifacts:
    async def test_log_artifact(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("artifact_test")
        art = await svc.log_artifact(
            exp.id, "model_v1.pkl",
            description="Trained XGBoost model",
            artifact_type="model",
            file_path="/artifacts/model_v1.pkl",
            file_size_bytes=45_000_000,
            uri="s3://bucket/models/model_v1.pkl",
            metadata={"framework": "xgboost"},
        )
        assert art.id is not None
        assert art.name == "model_v1.pkl"
        assert art.artifact_type == "model"

    async def test_get_artifacts(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("get_arts")
        await svc.log_artifact(exp.id, "a.pkl", artifact_type="model")
        await svc.log_artifact(exp.id, "b.csv", artifact_type="data")
        items = await svc.get_artifacts(exp.id)
        assert len(items) == 2

    async def test_get_artifacts_filter_type(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("filter_arts")
        await svc.log_artifact(exp.id, "model.pkl", artifact_type="model")
        await svc.log_artifact(exp.id, "data.csv", artifact_type="data")
        items = await svc.get_artifacts(exp.id, artifact_type="model")
        assert len(items) == 1


# ── Charts ──

class TestCharts:
    async def test_log_chart(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("chart_test")
        ch = await svc.log_chart(
            exp.id, "loss_curve",
            chart_type="line",
            chart_config={"x": "step", "y": "loss", "title": "Training Loss"},
            data={"steps": [1, 2, 3], "values": [0.5, 0.3, 0.1]},
        )
        assert ch.id is not None
        assert ch.name == "loss_curve"
        assert ch.chart_type == "line"

    async def test_get_charts(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("get_charts")
        await svc.log_chart(exp.id, "loss", chart_type="line")
        await svc.log_chart(exp.id, "accuracy", chart_type="line")
        items = await svc.get_charts(exp.id)
        assert len(items) == 2


# ── Tags ──

class TestTags:
    async def test_add_tag(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("tag_test")
        tag = await svc.add_tag(exp.id, "dataset", "stock_prices")
        assert tag.id is not None
        assert tag.key == "dataset"
        assert tag.value == "stock_prices"

    async def test_get_tags(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("get_tags")
        await svc.add_tag(exp.id, "a", "1")
        await svc.add_tag(exp.id, "b", "2")
        items = await svc.get_tags(exp.id)
        assert len(items) == 2

    async def test_find_by_tag(self, session):
        svc = ExperimentManagerService(session)
        e1 = await svc.create_experiment("exp1", tags={"dataset": "stocks"})
        e2 = await svc.create_experiment("exp2", tags={"dataset": "stocks"})
        e3 = await svc.create_experiment("exp3", tags={"dataset": "forex"})
        found = await svc.find_by_tag("dataset", "stocks")
        assert len(found) == 2
        assert e1.id in (f.id for f in found)
        assert e2.id in (f.id for f in found)


# ── Best Metric Direction ──

class TestBestMetric:
    async def test_set_best_metric_direction_max(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("best_max")
        await svc.log_metric(exp.id, "accuracy", 0.85)
        await svc.log_metric(exp.id, "accuracy", 0.92)
        await svc.log_metric(exp.id, "accuracy", 0.88)
        updated = await svc.set_best_metric_direction(exp.id, "accuracy", "max")
        assert updated.best_metric_name == "accuracy"
        assert updated.best_metric_value == 0.92

    async def test_set_best_metric_direction_min(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("best_min")
        await svc.log_metric(exp.id, "loss", 0.5)
        await svc.log_metric(exp.id, "loss", 0.3)
        await svc.log_metric(exp.id, "loss", 0.7)
        updated = await svc.set_best_metric_direction(exp.id, "loss", "min")
        assert updated.best_metric_name == "loss"
        assert updated.best_metric_value == 0.3

    async def test_auto_update_best_on_log(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("auto_best")
        await svc.set_best_metric_direction(exp.id, "accuracy", "max")
        await svc.log_metric(exp.id, "accuracy", 0.85)
        await svc.log_metric(exp.id, "accuracy", 0.95)
        exp_r = await svc.get_experiment(exp.id)
        assert exp_r.best_metric_value == 0.95


# ── Best Model Selection ──

class TestBestModel:
    async def test_find_best_experiment(self, session):
        svc = ExperimentManagerService(session)
        e1 = await svc.create_experiment("baseline", tags={"type": "tuning"})
        e2 = await svc.create_experiment("tuned", tags={"type": "tuning"})
        e3 = await svc.create_experiment("overfit", tags={"type": "test"})
        for exp in [e1, e2, e3]:
            await svc.update_experiment_status(exp.id, "completed")
        await svc.log_metric(e1.id, "accuracy", 0.80)
        await svc.log_metric(e1.id, "accuracy", 0.82)
        await svc.log_metric(e2.id, "accuracy", 0.91)
        await svc.log_metric(e2.id, "accuracy", 0.93)
        await svc.log_metric(e3.id, "accuracy", 0.70)

        best = await svc.find_best_experiment("accuracy", direction="max")
        assert best is not None
        assert best.id == e2.id

    async def test_find_best_with_tags(self, session):
        svc = ExperimentManagerService(session)
        e1 = await svc.create_experiment("tuned_a", tags={"dataset": "stocks", "type": "grid"})
        e2 = await svc.create_experiment("tuned_b", tags={"dataset": "stocks", "type": "grid"})
        e3 = await svc.create_experiment("forex_exp", tags={"dataset": "forex"})
        for exp in [e1, e2, e3]:
            await svc.update_experiment_status(exp.id, "completed")
        await svc.log_metric(e1.id, "f1", 0.85)
        await svc.log_metric(e2.id, "f1", 0.90)
        await svc.log_metric(e3.id, "f1", 0.75)

        best = await svc.find_best_experiment(
            "f1", direction="max", tags={"dataset": "stocks", "type": "grid"},
        )
        assert best is not None
        assert best.id == e2.id

    async def test_find_best_no_results(self, session):
        svc = ExperimentManagerService(session)
        assert await svc.find_best_experiment("accuracy") is None

    async def test_find_best_no_matching_tag(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment("only_exp", tags={"dataset": "stocks"})
        await svc.update_experiment_status(exp.id, "completed")
        await svc.log_metric(exp.id, "accuracy", 0.9)
        best = await svc.find_best_experiment("accuracy", tags={"dataset": "forex"})
        assert best is None


# ── Summary ──

class TestSummary:
    async def test_get_summary(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment(
            "summary_test", tags={"dataset": "stocks"},
        )
        await svc.log_parameter(exp.id, "lr", 0.01)
        await svc.log_metric(exp.id, "accuracy", 0.85)
        await svc.log_metric(exp.id, "accuracy", 0.90)
        await svc.log_metric(exp.id, "loss", 0.5)
        await svc.log_artifact(exp.id, "model.pkl", artifact_type="model")
        await svc.log_chart(exp.id, "loss_curve", chart_type="line")
        await svc.update_experiment_status(exp.id, "completed")

        summary = await svc.get_experiment_summary(exp.id)
        assert summary is not None
        assert summary["experiment"]["name"] == "summary_test"
        assert summary["experiment"]["status"] == "completed"
        assert "lr" in summary["parameters"]
        assert "accuracy" in summary["metrics"]
        assert summary["artifact_count"] == 1
        assert summary["chart_count"] == 1
        assert summary["tags"]["dataset"] == "stocks"
        assert summary["metrics"]["accuracy"]["max"] == 0.90
        assert summary["metrics"]["accuracy"]["min"] == 0.85

    async def test_get_summary_not_found(self, session):
        svc = ExperimentManagerService(session)
        assert await svc.get_experiment_summary(9999) is None


# ── Integration ──

class TestIntegration:
    async def test_full_experiment_lifecycle(self, session):
        svc = ExperimentManagerService(session)
        exp = await svc.create_experiment(
            "full_lifecycle",
            description="Integration test experiment",
            metadata={"purpose": "testing"},
            tags={"dataset": "integration"},
        )
        assert exp.status == "running"

        params = {"lr": 0.001, "batch_size": 32, "epochs": 10}
        await svc.log_parameters(exp.id, params)
        assert len(await svc.get_parameters(exp.id)) == 3

        for epoch in range(1, 6):
            await svc.log_metric(exp.id, "loss", 0.5 / epoch, step=epoch, epoch=epoch)
            await svc.log_metric(exp.id, "accuracy", 0.7 + epoch * 0.05, step=epoch, epoch=epoch)

        await svc.set_best_metric_direction(exp.id, "accuracy", "max")
        await svc.log_metric(exp.id, "accuracy", 0.96, step=6)

        exp_r = await svc.get_experiment(exp.id)
        assert exp_r.best_metric_value == 0.96
        assert exp_r.best_metric_name == "accuracy"

        await svc.log_artifact(exp.id, "final_model.pkl", artifact_type="model", uri="s3://models/final.pkl")
        await svc.log_chart(exp.id, "accuracy_curve", chart_type="line", chart_config={"x": "epoch", "y": "accuracy"})

        await svc.update_experiment_status(exp.id, "completed")

        summary = await svc.get_experiment_summary(exp.id)
        assert summary["experiment"]["status"] == "completed"
        assert summary["artifact_count"] == 1
        assert summary["chart_count"] == 1
        assert summary["tags"]["dataset"] == "integration"

        best = await svc.find_best_experiment("accuracy", tags={"dataset": "integration"})
        assert best is not None
        assert best.id == exp.id
