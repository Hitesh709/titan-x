import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.automated_training import (
    DatasetVersion,
    FeatureSet,
    HyperparameterConfig,
    TrainingJob,
    TrainingJobCheckpoint,
    TrainingJobLog,
)
from titan_x.services.automated_training_service import AutomatedTrainingService

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


# ── Dataset Versioning ──

class TestDatasets:
    async def test_create_dataset(self, session):
        svc = AutomatedTrainingService(session)
        ds = await svc.create_dataset(
            name="ohlc_1min", version="1.0.0",
            description="1-minute OHLC data",
            source="s3://data/ohlc_1min_v1",
            row_count=1_000_000, size_bytes=50_000_000,
            checksum="abc123",
            metadata={"granularity": "1min"},
        )
        assert ds.id is not None
        assert ds.name == "ohlc_1min"
        assert ds.version == "1.0.0"
        assert ds.row_count == 1_000_000
        assert ds.status == "active"

    async def test_get_dataset(self, session):
        svc = AutomatedTrainingService(session)
        ds = await svc.create_dataset("test_ds", "1.0")
        got = await svc.get_dataset(ds.id)
        assert got is not None
        assert got.id == ds.id

    async def test_get_dataset_not_found(self, session):
        svc = AutomatedTrainingService(session)
        assert await svc.get_dataset(9999) is None

    async def test_list_datasets(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_dataset("a", "1.0")
        await svc.create_dataset("b", "2.0")
        items = await svc.list_datasets()
        assert len(items) == 2

    async def test_list_datasets_pagination(self, session):
        svc = AutomatedTrainingService(session)
        for i in range(5):
            await svc.create_dataset(f"ds_{i}", f"1.{i}")
        items = await svc.list_datasets(limit=2, offset=1)
        assert len(items) == 2


# ── Feature Sets ──

class TestFeatureSets:
    async def test_create_feature_set(self, session):
        svc = AutomatedTrainingService(session)
        fs = await svc.create_feature_set(
            name="price_momentum",
            features=["open", "high", "low", "close", "volume", "rsi_14"],
            target_column="next_return",
            metadata={"type": "regression"},
        )
        assert fs.id is not None
        assert fs.name == "price_momentum"
        assert fs.feature_count == 6
        assert fs.target_column == "next_return"

    async def test_get_feature_set(self, session):
        svc = AutomatedTrainingService(session)
        fs = await svc.create_feature_set("test_fs")
        got = await svc.get_feature_set(fs.id)
        assert got is not None
        assert got.id == fs.id

    async def test_get_feature_set_not_found(self, session):
        svc = AutomatedTrainingService(session)
        assert await svc.get_feature_set(9999) is None

    async def test_list_feature_sets(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_feature_set("a")
        await svc.create_feature_set("b")
        items = await svc.list_feature_sets()
        assert len(items) == 2

    async def test_create_without_optional(self, session):
        svc = AutomatedTrainingService(session)
        fs = await svc.create_feature_set("minimal")
        assert fs.feature_count is None
        assert fs.target_column is None


# ── Hyperparameter Configs ──

class TestHyperparameterConfig:
    async def test_create_hp_config(self, session):
        svc = AutomatedTrainingService(session)
        hp = await svc.create_hyperparameter_config(
            name="xgboost_default",
            parameters={
                "learning_rate": 0.1,
                "max_depth": 6,
                "n_estimators": 100,
                "subsample": 0.8,
            },
            description="Default XGBoost params",
        )
        assert hp.id is not None
        assert hp.name == "xgboost_default"
        assert hp.parameters_json is not None

    async def test_get_hp_config(self, session):
        svc = AutomatedTrainingService(session)
        hp = await svc.create_hyperparameter_config("test_hp")
        got = await svc.get_hyperparameter_config(hp.id)
        assert got is not None and got.id == hp.id

    async def test_list_hp_configs(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_hyperparameter_config("a")
        await svc.create_hyperparameter_config("b")
        items = await svc.list_hyperparameter_configs()
        assert len(items) == 2


# ── Training Jobs ──

class TestTrainingJobs:
    async def test_create_job(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job(
            name="xgboost_train_v1",
            description="First XGBoost training run",
            max_epochs=50,
            priority=10,
            gpu_required=True,
            gpu_memory_required_mb=4096,
        )
        assert job.id is not None
        assert job.name == "xgboost_train_v1"
        assert job.status == "pending"
        assert job.gpu_required is True
        assert job.gpu_memory_required_mb == 4096
        assert job.current_epoch == 0

    async def test_create_job_with_refs(self, session):
        svc = AutomatedTrainingService(session)
        ds = await svc.create_dataset("ds", "1.0")
        fs = await svc.create_feature_set("fs")
        hp = await svc.create_hyperparameter_config("hp", parameters={"lr": 0.01})
        job = await svc.create_job(
            "job_with_refs",
            dataset_version_id=ds.id,
            feature_set_id=fs.id,
            hyperparameter_config_id=hp.id,
        )
        assert job.dataset_version_id == ds.id
        assert job.feature_set_id == fs.id
        assert job.hyperparameter_config_id == hp.id

    async def test_get_job(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("test_job")
        got = await svc.get_job(job.id)
        assert got is not None and got.id == job.id

    async def test_get_job_not_found(self, session):
        svc = AutomatedTrainingService(session)
        assert await svc.get_job(9999) is None

    async def test_list_jobs(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_job("a")
        await svc.create_job("b")
        items = await svc.list_jobs()
        assert len(items) == 2

    async def test_list_jobs_filter_status(self, session):
        svc = AutomatedTrainingService(session)
        j1 = await svc.create_job("running_job")
        j2 = await svc.create_job("pending_job")
        await svc.update_job_status(j1.id, "running")
        items = await svc.list_jobs(status="running")
        assert len(items) == 1
        assert items[0].id == j1.id

    async def test_update_job_status(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("status_test")
        updated = await svc.update_job_status(job.id, "running")
        assert updated is not None
        assert updated.status == "running"
        assert updated.started_at is not None

    async def test_update_job_status_completed(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("complete_test")
        await svc.update_job_status(job.id, "running")
        done = await svc.update_job_status(job.id, "completed")
        assert done is not None
        assert done.status == "completed"
        assert done.completed_at is not None

    async def test_update_job_status_failed(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("fail_test")
        failed = await svc.update_job_status(job.id, "failed", error_message="OOM")
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_message == "OOM"

    async def test_update_job_progress(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("progress_test", max_epochs=10)
        await svc.update_job_progress(
            job.id,
            current_epoch=5, current_step=200,
            loss_value=0.25, best_loss=0.20,
            metric_value=0.85, best_metric=0.90,
            training_duration_seconds=120.5,
        )
        updated = await svc.get_job(job.id)
        assert updated.current_epoch == 5
        assert updated.loss_value == 0.25
        assert updated.best_metric == 0.90
        assert updated.training_duration_seconds == 120.5


# ── Checkpointing ──

class TestCheckpoints:
    async def test_create_checkpoint(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("cp_job", max_epochs=10)
        cp = await svc.create_checkpoint(
            job.id, epoch=3, step=120,
            metric_value=0.88, loss_value=0.22,
            artifact_path="/checkpoints/cp_job_epoch_3.pt",
            file_size_bytes=45_000_000,
            metadata={"optimizer_step": 120},
        )
        assert cp.id is not None
        assert cp.job_id == job.id
        assert cp.epoch == 3

    async def test_get_latest_checkpoint(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("latest_cp")
        await svc.create_checkpoint(job.id, epoch=1, metric_value=0.7)
        await svc.create_checkpoint(job.id, epoch=2, metric_value=0.8)
        await svc.create_checkpoint(job.id, epoch=3, metric_value=0.9)
        cp = await svc.get_latest_checkpoint(job.id)
        assert cp is not None
        assert cp.epoch == 3
        assert cp.metric_value == 0.9

    async def test_get_latest_checkpoint_empty(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("no_cp")
        assert await svc.get_latest_checkpoint(job.id) is None

    async def test_list_checkpoints(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("list_cp")
        for e in range(1, 4):
            await svc.create_checkpoint(job.id, epoch=e)
        items = await svc.list_checkpoints(job.id)
        assert len(items) == 3


# ── Resume ──

class TestResume:
    async def test_resume_failed_job(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("resume_fail")
        await svc.update_job_status(job.id, "failed", error_message="OOM")
        await svc.create_checkpoint(job.id, epoch=2, metric_value=0.75)
        resumed = await svc.resume_job(job.id)
        assert resumed is not None
        assert resumed.status == "running"
        resumed_cp = await svc.get_latest_checkpoint(job.id)
        assert resumed_cp is not None

    async def test_resume_paused_job(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("resume_pause")
        await svc.update_job_status(job.id, "paused")
        resumed = await svc.resume_job(job.id)
        assert resumed is not None and resumed.status == "running"

    async def test_resume_not_found(self, session):
        svc = AutomatedTrainingService(session)
        assert await svc.resume_job(9999) is None

    async def test_resume_already_running(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("already_run")
        await svc.update_job_status(job.id, "running")
        assert await svc.resume_job(job.id) is None


# ── Logging ──

class TestLogs:
    async def test_add_log(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("log_job")
        log = await svc.add_log(job.id, "info", "Training started", epoch=0, step=0)
        assert log.id is not None
        assert log.level == "info"
        assert log.message == "Training started"
        assert log.epoch == 0

    async def test_get_logs(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("get_logs")
        await svc.add_log(job.id, "info", "msg1")
        await svc.add_log(job.id, "warning", "msg2")
        await svc.add_log(job.id, "error", "msg3")
        items = await svc.get_logs(job.id)
        assert len(items) == 3

    async def test_get_logs_filter_level(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("filter_logs")
        await svc.add_log(job.id, "info", "msg1")
        await svc.add_log(job.id, "error", "msg2")
        items = await svc.get_logs(job.id, level="error")
        assert len(items) == 1
        assert items[0].level == "error"

    async def test_logs_empty(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("empty_logs")
        assert await svc.get_logs(job.id) == []


# ── Scheduling ──

class TestScheduling:
    async def test_get_pending_jobs(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_job("pending1")
        await svc.create_job("pending2")
        j3 = await svc.create_job("running1")
        await svc.update_job_status(j3.id, "running")
        items = await svc.get_pending_jobs()
        assert len(items) == 2

    async def test_get_running_jobs(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_job("p1")
        j2 = await svc.create_job("r1")
        await svc.update_job_status(j2.id, "running")
        items = await svc.get_running_jobs()
        assert len(items) == 1
        assert items[0].id == j2.id

    async def test_get_gpu_jobs(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_job("cpu1", gpu_required=False)
        j2 = await svc.create_job("gpu1", gpu_required=True)
        j3 = await svc.create_job("gpu2", gpu_required=True)
        items = await svc.get_gpu_jobs()
        assert len(items) == 2

    async def test_get_due_scheduled_jobs(self, session):
        svc = AutomatedTrainingService(session)
        await svc.create_job("scheduled1", schedule="0 3 * * *")
        await svc.create_job("scheduled2", schedule="0 4 * * *")
        j3 = await svc.create_job("no_schedule")
        items = await svc.get_due_scheduled_jobs()
        assert len(items) == 2


# ── Integration: full lifecycle ──

class TestIntegration:
    async def test_full_job_lifecycle(self, session):
        svc = AutomatedTrainingService(session)
        ds = await svc.create_dataset("train_data", "1.0", row_count=500_000)
        fs = await svc.create_feature_set("momentum", features=["close", "volume"], target_column="ret")
        hp = await svc.create_hyperparameter_config("lgbm_default", parameters={"lr": 0.05, "leaves": 31})

        job = await svc.create_job(
            "lgbm_train",
            dataset_version_id=ds.id,
            feature_set_id=fs.id,
            hyperparameter_config_id=hp.id,
            max_epochs=10,
            gpu_required=True,
        )
        assert job.status == "pending"

        await svc.add_log(job.id, "info", "Starting training")
        started = await svc.update_job_status(job.id, "running")
        assert started.status == "running"

        for epoch in range(1, 11):
            await svc.update_job_progress(
                job.id,
                current_epoch=epoch,
                loss_value=max(0.5 - epoch * 0.04, 0.05),
                best_loss=0.05,
                metric_value=min(epoch * 0.08, 0.95),
                best_metric=0.95,
            )
            await svc.add_log(job.id, "info", f"Epoch {epoch} complete", epoch=epoch)
            if epoch % 3 == 0:
                await svc.create_checkpoint(
                    job.id, epoch=epoch, metric_value=0.7 + epoch * 0.02,
                    artifact_path=f"/checkpoints/lgbm_epoch_{epoch}.pt",
                )

        await svc.update_job_status(job.id, "completed")
        final = await svc.get_job(job.id)
        assert final.status == "completed"
        assert final.current_epoch == 10
        assert final.completed_at is not None

        logs = await svc.get_logs(job.id)
        assert len(logs) == 11

        cps = await svc.list_checkpoints(job.id)
        assert len(cps) == 3

    async def test_fail_and_resume(self, session):
        svc = AutomatedTrainingService(session)
        job = await svc.create_job("fail_resume", max_epochs=20)

        await svc.update_job_status(job.id, "running")
        await svc.update_job_progress(job.id, current_epoch=5, loss_value=0.3)
        await svc.create_checkpoint(job.id, epoch=5, metric_value=0.7)
        await svc.add_log(job.id, "error", "CUDA OOM", epoch=5)
        await svc.update_job_status(job.id, "failed", error_message="CUDA OOM")

        failed_job = await svc.get_job(job.id)
        assert failed_job.status == "failed"
        assert failed_job.error_message == "CUDA OOM"

        resumed = await svc.resume_job(job.id)
        assert resumed.status == "running"

        cp = await svc.get_latest_checkpoint(job.id)
        assert cp.epoch == 5
