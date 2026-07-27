import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin
from titan_x.db.repository import BaseRepository


class SampleModel(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sample_models"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def repo(session: AsyncSession) -> BaseRepository[SampleModel]:
    return BaseRepository(session, SampleModel)


@pytest.mark.asyncio
async def test_create(repo: BaseRepository[SampleModel]) -> None:
    instance = await repo.create(name="test", active=True)
    assert instance.id is not None
    assert instance.name == "test"
    assert instance.active is True


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(repo: BaseRepository[SampleModel]) -> None:
    result = await repo.get(999)
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_instance(repo: BaseRepository[SampleModel]) -> None:
    created = await repo.create(name="find-me")
    result = await repo.get(created.id)
    assert result is not None
    assert result.name == "find-me"


@pytest.mark.asyncio
async def test_get_multi_with_filters(repo: BaseRepository[SampleModel]) -> None:
    await repo.create(name="a", active=True)
    await repo.create(name="b", active=False)
    await repo.create(name="c", active=True)

    results = await repo.get_multi(active=True)
    assert len(results) == 2

    results = await repo.get_multi(active=False)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_get_multi_pagination(repo: BaseRepository[SampleModel]) -> None:
    for i in range(10):
        await repo.create(name=f"item-{i}")

    page = await repo.get_multi(skip=0, limit=3)
    assert len(page) == 3

    page2 = await repo.get_multi(skip=3, limit=3)
    assert len(page2) == 3
    assert page2[0].name == "item-3"


@pytest.mark.asyncio
async def test_update(repo: BaseRepository[SampleModel]) -> None:
    created = await repo.create(name="original")
    updated = await repo.update(created.id, name="updated")
    assert updated is not None
    assert updated.name == "updated"


@pytest.mark.asyncio
async def test_delete(repo: BaseRepository[SampleModel]) -> None:
    created = await repo.create(name="delete-me")
    deleted = await repo.delete(created.id)
    assert deleted is True
    assert await repo.get(created.id) is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing(repo: BaseRepository[SampleModel]) -> None:
    result = await repo.delete(999)
    assert result is False


@pytest.mark.asyncio
async def test_count(repo: BaseRepository[SampleModel]) -> None:
    assert await repo.count() == 0
    await repo.create(name="x")
    assert await repo.count() == 1
