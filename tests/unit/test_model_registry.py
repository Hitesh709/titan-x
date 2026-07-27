from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.model_registry import (
    ModelMetric,
    ModelRegistryDeployment,
    ModelRegistryEntry,
    ModelRegistryVersion,
    ModelTrainingRun,
)
from titan_x.services.model_registry_service import ModelRegistryService

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


@pytest_asyncio.fixture
async def svc(session):
    return ModelRegistryService(session)


class TestEntryCRUD:
    async def test_register_entry(self, svc):
        e = await svc.register_entry(
            name="sentiment-bert", model_type="nlp",
            description="BERT-based sentiment analysis",
            framework="pytorch",
            tags=["nlp", "sentiment"],
            metadata={"vocab_size": 30522},
        )
        assert e.id is not None
        assert e.name == "sentiment-bert"
        assert e.model_type == "nlp"
        assert e.status == "active"

    async def test_register_duplicate_name_raises(self, svc):
        await svc.register_entry(name="dup", model_type="ml")
        with pytest.raises(Exception):
            await svc.register_entry(name="dup", model_type="ml")

    async def test_get_entry(self, svc):
        e = await svc.register_entry(name="test", model_type="ml")
        found = await svc.get_entry(e.id)
        assert found is not None
        assert found.id == e.id

    async def test_get_entry_not_found(self, svc):
        assert await svc.get_entry(9999) is None

    async def test_get_entry_by_name(self, svc):
        e = await svc.register_entry(name="my-model", model_type="ml")
        found = await svc.get_entry_by_name("my-model")
        assert found is not None
        assert found.id == e.id

    async def test_list_entries(self, svc):
        await svc.register_entry(name="a", model_type="ml")
        await svc.register_entry(name="b", model_type="ensemble")
        entries = await svc.list_entries()
        assert len(entries) >= 2

    async def test_list_entries_filter_type(self, svc):
        await svc.register_entry(name="a", model_type="ml")
        await svc.register_entry(name="b", model_type="ensemble")
        entries = await svc.list_entries(model_type="ml")
        assert len(entries) == 1

    async def test_update_entry(self, svc):
        e = await svc.register_entry(name="updatable", model_type="ml")
        updated = await svc.update_entry(e.id, description="new desc", framework="tf")
        assert updated is not None
        assert updated.description == "new desc"
        assert updated.framework == "tf"

    async def test_update_entry_not_found(self, svc):
        assert await svc.update_entry(9999, description="x") is None


class TestVersionCRUD:
    async def test_create_version(self, svc):
        e = await svc.register_entry(name="vtest", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0", description="initial", changelog="first release")
        assert v.version == "1.0.0"
        assert v.status == "draft"
        assert not v.is_active

    async def test_list_versions(self, svc):
        e = await svc.register_entry(name="vlist", model_type="ml")
        await svc.create_version(e.id, "1.0.0")
        await svc.create_version(e.id, "2.0.0")
        versions = await svc.get_versions(e.id)
        assert len(versions) == 2

    async def test_update_version(self, svc):
        e = await svc.register_entry(name="vupd", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        updated = await svc.update_version(v.id, status="active", description="updated desc")
        assert updated is not None
        assert updated.status == "active"
        assert updated.description == "updated desc"


class TestActiveVersion:
    async def test_set_active_version(self, svc):
        e = await svc.register_entry(name="act", model_type="ml")
        v1 = await svc.create_version(e.id, "1.0.0")
        v2 = await svc.create_version(e.id, "2.0.0")
        activated = await svc.set_active_version(v2.id)
        assert activated is not None
        assert activated.is_active

        active = await svc.get_active_version(e.id)
        assert active is not None
        assert active.id == v2.id

    async def test_set_active_deactivates_previous(self, svc):
        e = await svc.register_entry(name="act2", model_type="ml")
        v1 = await svc.create_version(e.id, "1.0.0")
        v2 = await svc.create_version(e.id, "2.0.0")
        await svc.set_active_version(v1.id)
        await svc.set_active_version(v2.id)

        r1 = await svc.get_version(v1.id)
        assert r1 is not None
        assert not r1.is_active

    async def test_get_active_version_by_entry_name(self, svc):
        e = await svc.register_entry(name="findme", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        await svc.set_active_version(v.id)
        active = await svc.get_active_version_by_entry_name("findme")
        assert active is not None
        assert active.id == v.id


class TestTrainingRuns:
    async def test_create_training_run(self, svc):
        e = await svc.register_entry(name="tr", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        tr = await svc.create_training_run(
            version_id=v.id,
            run_id="run_001",
            dataset_info={"name": "dataset_v3", "split": "train"},
            hyperparameters={"lr": 0.001, "epochs": 10},
            training_duration_seconds=3600,
            metrics={"accuracy": 0.95, "loss": 0.12},
            artifact_path="s3://models/v1/",
            notes="First training run",
        )
        assert tr.run_id == "run_001"
        assert tr.training_duration_seconds == 3600.0

    async def test_list_training_runs(self, svc):
        e = await svc.register_entry(name="trl", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        await svc.create_training_run(v.id, run_id="r1")
        await svc.create_training_run(v.id, run_id="r2")
        runs = await svc.list_training_runs(v.id)
        assert len(runs) == 2

    async def test_get_training_run(self, svc):
        e = await svc.register_entry(name="trg", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        tr = await svc.create_training_run(v.id, run_id="findme")
        found = await svc.get_training_run(tr.id)
        assert found is not None
        assert found.run_id == "findme"


class TestMetrics:
    async def test_record_metric(self, svc):
        e = await svc.register_entry(name="met", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        m = await svc.record_metric(v.id, "accuracy", 0.95, dataset_type="validation")
        assert m.metric_name == "accuracy"
        assert m.metric_value == 0.95

    async def test_get_metrics(self, svc):
        e = await svc.register_entry(name="metl", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        await svc.record_metric(v.id, "accuracy", 0.95, dataset_type="validation")
        await svc.record_metric(v.id, "f1", 0.93, dataset_type="validation")
        await svc.record_metric(v.id, "accuracy", 0.91, dataset_type="train")
        metrics = await svc.get_metrics(v.id)
        assert len(metrics) == 3

    async def test_get_metrics_filter_name(self, svc):
        e = await svc.register_entry(name="metf", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        await svc.record_metric(v.id, "accuracy", 0.95)
        await svc.record_metric(v.id, "f1", 0.93)
        metrics = await svc.get_metrics(v.id, metric_name="accuracy")
        assert len(metrics) == 1
        assert metrics[0].metric_name == "accuracy"

    async def test_get_metrics_filter_dataset(self, svc):
        e = await svc.register_entry(name="metfd", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        await svc.record_metric(v.id, "accuracy", 0.95, dataset_type="validation")
        await svc.record_metric(v.id, "accuracy", 0.91, dataset_type="train")
        metrics = await svc.get_metrics(v.id, dataset_type="train")
        assert len(metrics) == 1


class TestDeploymentAndRollback:
    async def test_deploy(self, svc):
        e = await svc.register_entry(name="dep", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        dep = await svc.deploy(v.id, "production", deployed_by="tester", notes="First deploy")
        assert dep.environment == "production"
        assert dep.status == "active"

    async def test_deploy_switches_active(self, svc):
        e = await svc.register_entry(name="depsw", model_type="ml")
        v1 = await svc.create_version(e.id, "1.0.0")
        v2 = await svc.create_version(e.id, "2.0.0")
        await svc.deploy(v1.id, "production")
        await svc.deploy(v2.id, "production")
        active = await svc.get_active_deployment("production")
        assert active is not None
        assert active.version_id == v2.id

    async def test_rollback(self, svc):
        e = await svc.register_entry(name="rb", model_type="ml")
        v1 = await svc.create_version(e.id, "1.0.0")
        v2 = await svc.create_version(e.id, "2.0.0")
        await svc.deploy(v1.id, "production")
        await svc.deploy(v2.id, "production")
        dep = await svc.rollback("production", rolled_by="tester")
        assert dep is not None
        assert dep.version_id == v1.id
        assert dep.status == "active"

    async def test_rollback_no_target(self, svc):
        e = await svc.register_entry(name="rbn", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        await svc.deploy(v.id, "production")
        dep = await svc.rollback("production")
        assert dep is None

    async def test_get_active_deployment(self, svc):
        e = await svc.register_entry(name="gad", model_type="ml")
        v = await svc.create_version(e.id, "1.0.0")
        await svc.deploy(v.id, "staging")
        dep = await svc.get_active_deployment("staging")
        assert dep is not None
        assert dep.environment == "staging"

    async def test_get_deployment_history(self, svc):
        e = await svc.register_entry(name="hist", model_type="ml")
        v1 = await svc.create_version(e.id, "1.0.0")
        v2 = await svc.create_version(e.id, "2.0.0")
        await svc.deploy(v1.id, "production")
        await svc.deploy(v2.id, "production")
        history = await svc.get_deployment_history("production")
        assert len(history) >= 2


class TestCompare:
    async def test_compare_versions(self, svc):
        e = await svc.register_entry(name="comp", model_type="ml")
        v1 = await svc.create_version(e.id, "1.0.0")
        v2 = await svc.create_version(e.id, "2.0.0")
        await svc.record_metric(v1.id, "accuracy", 0.90)
        await svc.record_metric(v2.id, "accuracy", 0.95)
        await svc.deploy(v2.id, "production")
        results = await svc.compare_versions([v1.id, v2.id])
        assert len(results) == 2
        r2 = next(r for r in results if r["version_id"] == v2.id)
        assert r2["is_active"] is False
        assert len(r2["metrics"]) == 1
        assert len(r2["deployments"]) == 1
