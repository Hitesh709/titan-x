import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.user import User
from titan_x.services.preference_service import PreferenceService


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
    u = User(email="prefs@test.com", hashed_password="hash")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> PreferenceService:
    return PreferenceService(session)


class TestPreferences:
    @pytest.mark.asyncio
    async def test_get_not_found(self, svc: PreferenceService, user: User):
        value = await svc.get_preference(user.id, "nonexistent")
        assert value is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, svc: PreferenceService, user: User):
        pref = await svc.set_preference(user.id, "theme", "dark")
        assert pref.pref_key == "theme"
        assert pref.pref_value == "dark"
        assert pref.user_id == user.id

        value = await svc.get_preference(user.id, "theme")
        assert value == "dark"

    @pytest.mark.asyncio
    async def test_update_existing(self, svc: PreferenceService, user: User):
        await svc.set_preference(user.id, "theme", "dark")
        await svc.set_preference(user.id, "theme", "light")

        value = await svc.get_preference(user.id, "theme")
        assert value == "light"

    @pytest.mark.asyncio
    async def test_get_all(self, svc: PreferenceService, user: User):
        await svc.set_preference(user.id, "a", "1")
        await svc.set_preference(user.id, "b", "2")

        all_prefs = await svc.get_all_preferences(user.id)
        assert all_prefs == {"a": "1", "b": "2"}

    @pytest.mark.asyncio
    async def test_get_all_empty(self, svc: PreferenceService, user: User):
        all_prefs = await svc.get_all_preferences(user.id)
        assert all_prefs == {}

    @pytest.mark.asyncio
    async def test_delete(self, svc: PreferenceService, user: User):
        await svc.set_preference(user.id, "temp", "value")
        ok = await svc.delete_preference(user.id, "temp")
        assert ok is True

        value = await svc.get_preference(user.id, "temp")
        assert value is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, svc: PreferenceService, user: User):
        ok = await svc.delete_preference(user.id, "nonexistent")
        assert ok is False

    @pytest.mark.asyncio
    async def test_delete_all(self, svc: PreferenceService, user: User):
        await svc.set_preference(user.id, "a", "1")
        await svc.set_preference(user.id, "b", "2")

        count = await svc.delete_all_preferences(user.id)
        assert count == 2

        all_prefs = await svc.get_all_preferences(user.id)
        assert all_prefs == {}

    @pytest.mark.asyncio
    async def test_delete_all_empty(self, svc: PreferenceService, user: User):
        count = await svc.delete_all_preferences(user.id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_multi_user_isolation(self, svc: PreferenceService, session: AsyncSession):
        u1 = User(email="u1@test.com", hashed_password="hash")
        u2 = User(email="u2@test.com", hashed_password="hash")
        session.add(u1)
        session.add(u2)
        await session.flush()

        await svc.set_preference(u1.id, "key", "u1_value")
        await svc.set_preference(u2.id, "key", "u2_value")

        assert await svc.get_preference(u1.id, "key") == "u1_value"
        assert await svc.get_preference(u2.id, "key") == "u2_value"
