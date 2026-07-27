import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.ai_registry import AIModelRegistry, ModelDeployment
from titan_x.models.user import User
from titan_x.services.ai_registry_service import AIModelRegistryService


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
async def user(session: AsyncSession) -> User:
    u = User(email="ai_reg@test.com", hashed_password="hash")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> AIModelRegistryService:
    return AIModelRegistryService(session)


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_model(self, svc: AIModelRegistryService):
        m = await svc.register(
            name="ensemble-v1",
            version="1.0.0",
            model_type="ensemble",
            description="Initial ensemble model",
            source="training_pipeline",
            metrics_json='{"accuracy": 0.85}',
        )
        assert m.name == "ensemble-v1"
        assert m.version == "1.0.0"
        assert m.model_type == "ensemble"
        assert m.status == "draft"
        assert m.metrics_json == '{"accuracy": 0.85}'

    @pytest.mark.asyncio
    async def test_register_duplicate_raises(self, svc: AIModelRegistryService):
        await svc.register(name="test", version="1.0", model_type="ml")
        with pytest.raises(Exception):
            await svc.register(name="test", version="1.0", model_type="ml")


class TestGetList:
    @pytest.mark.asyncio
    async def test_get_not_found(self, svc: AIModelRegistryService):
        assert await svc.get(9999) is None

    @pytest.mark.asyncio
    async def test_get(self, svc: AIModelRegistryService):
        m = await svc.register(name="m1", version="1", model_type="technical")
        fetched = await svc.get(m.id)
        assert fetched is not None
        assert fetched.id == m.id

    @pytest.mark.asyncio
    async def test_get_by_name(self, svc: AIModelRegistryService):
        await svc.register(name="m1", version="1", model_type="a")
        await svc.register(name="m1", version="2", model_type="a")
        versions = await svc.get_by_name("m1")
        assert len(versions) == 2

    @pytest.mark.asyncio
    async def test_list_empty(self, svc: AIModelRegistryService):
        rows, total = await svc.list()
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_filter_type(self, svc: AIModelRegistryService):
        await svc.register(name="a", version="1", model_type="technical")
        await svc.register(name="b", version="1", model_type="fundamental")
        rows, total = await svc.list(model_type="technical")
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_filter_status(self, svc: AIModelRegistryService):
        m = await svc.register(name="a", version="1", model_type="ml")
        await svc.change_status(m.id, "active")
        await svc.register(name="b", version="1", model_type="ml")
        rows, total = await svc.list(status="active")
        assert total == 1


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_not_found(self, svc: AIModelRegistryService):
        assert await svc.update(9999, description="new") is None

    @pytest.mark.asyncio
    async def test_update(self, svc: AIModelRegistryService):
        m = await svc.register(name="m", version="1", model_type="ml")
        updated = await svc.update(m.id, description="Updated desc", source="new_source")
        assert updated is not None
        assert updated.description == "Updated desc"
        assert updated.source == "new_source"


class TestStatus:
    @pytest.mark.asyncio
    async def test_change_status(self, svc: AIModelRegistryService):
        m = await svc.register(name="m", version="1", model_type="ml")
        updated = await svc.change_status(m.id, "active")
        assert updated.status == "active"

    @pytest.mark.asyncio
    async def test_change_status_not_found(self, svc: AIModelRegistryService):
        assert await svc.change_status(9999, "active") is None

    @pytest.mark.asyncio
    async def test_change_status_invalid(self, svc: AIModelRegistryService):
        m = await svc.register(name="m", version="1", model_type="ml")
        with pytest.raises(ValueError, match="Invalid status"):
            await svc.change_status(m.id, "invalid")


class TestDeploy:
    @pytest.mark.asyncio
    async def test_deploy(self, svc: AIModelRegistryService):
        m = await svc.register(name="m", version="1", model_type="ml")
        d = await svc.deploy(m.id, "dev", deployed_by="test_user")
        assert d.model_id == m.id
        assert d.environment == "dev"
        assert d.status == "active"
        assert d.deployed_by == "test_user"

    @pytest.mark.asyncio
    async def test_deploy_invalid_env(self, svc: AIModelRegistryService):
        m = await svc.register(name="m", version="1", model_type="ml")
        with pytest.raises(ValueError, match="Environment must be"):
            await svc.deploy(m.id, "invalid")

    @pytest.mark.asyncio
    async def test_deploy_redeploy(self, svc: AIModelRegistryService):
        m = await svc.register(name="m", version="1", model_type="ml")
        await svc.deploy(m.id, "dev")
        d2 = await svc.deploy(m.id, "dev", deployed_by="someone")
        assert d2.status == "active"
        assert d2.deployed_by == "someone"

    @pytest.mark.asyncio
    async def test_get_deployments(self, svc: AIModelRegistryService):
        m = await svc.register(name="m", version="1", model_type="ml")
        await svc.deploy(m.id, "dev")
        await svc.deploy(m.id, "staging")
        deps = await svc.get_deployments(m.id)
        assert len(deps) == 2

    @pytest.mark.asyncio
    async def test_compare(self, svc: AIModelRegistryService):
        m1 = await svc.register(name="m1", version="1", model_type="ml", metrics_json='{"acc": 0.8}')
        m2 = await svc.register(name="m2", version="1", model_type="ml", metrics_json='{"acc": 0.9}')
        await svc.deploy(m1.id, "production")
        results = await svc.compare([m1.id, m2.id])
        assert len(results) == 2
        r1 = next(r for r in results if r["id"] == m1.id)
        assert r1["name"] == "m1"
        assert len(r1["deployments"]) == 1
