import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings
from titan_x.db.base import Base
from titan_x.models.user import User
from titan_x.services.user_service import UserService

_settings = Settings(
    database_url="sqlite+aiosqlite:///",
    redis_url="redis://localhost:6379/0",
    api_key="a" * 32,
    jwt_secret_key="b" * 32,
    environment="test",
)


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
async def service(session: AsyncSession) -> UserService:
    return UserService(session, _settings)


@pytest.mark.asyncio
async def test_create_user(service: UserService) -> None:
    user = await service.create_user(email="new@test.com", password="Str0ng!Pass")
    assert user.id is not None
    assert user.email == "new@test.com"
    assert user.role == "normal"


@pytest.mark.asyncio
async def test_create_user_with_custom_role(service: UserService) -> None:
    user = await service.create_user(email="admin@test.com", password="Str0ng!Pass", role="admin", is_superuser=True)
    assert user.role == "admin"
    assert user.is_superuser is True


@pytest.mark.asyncio
async def test_create_duplicate_email_raises(service: UserService) -> None:
    await service.create_user(email="dup@test.com", password="Str0ng!Pass")
    with pytest.raises(ValueError, match="Email already registered"):
        await service.create_user(email="dup@test.com", password="Other!1")


@pytest.mark.asyncio
async def test_get_by_id(service: UserService) -> None:
    created = await service.create_user(email="get@test.com", password="Str0ng!Pass")
    found = await service.get_by_id(created.id)
    assert found is not None
    assert found.email == "get@test.com"


@pytest.mark.asyncio
async def test_get_by_id_missing(service: UserService) -> None:
    assert await service.get_by_id(999) is None


@pytest.mark.asyncio
async def test_get_by_email(service: UserService) -> None:
    await service.create_user(email="byemail@test.com", password="Str0ng!Pass")
    found = await service.get_by_email("byemail@test.com")
    assert found is not None
    assert found.email == "byemail@test.com"


@pytest.mark.asyncio
async def test_list_users_pagination(service: UserService) -> None:
    for i in range(10):
        await service.create_user(email=f"user{i}@test.com", password="Str0ng!Pass")
    users, total = await service.list_users(skip=0, limit=3)
    assert len(users) == 3
    assert total == 10


@pytest.mark.asyncio
async def test_list_users_search(service: UserService) -> None:
    await service.create_user(email="alice@test.com", password="Str0ng!Pass")
    await service.create_user(email="bob@test.com", password="Str0ng!Pass")
    await service.create_user(email="alex@test.com", password="Str0ng!Pass")
    users, total = await service.list_users(search="ali")
    assert total == 1
    assert users[0].email == "alice@test.com"

    users2, total2 = await service.list_users(search="al")
    assert total2 == 2


@pytest.mark.asyncio
async def test_list_users_filter_by_role(service: UserService) -> None:
    await service.create_user(email="normal@test.com", password="Str0ng!Pass", role="normal")
    await service.create_user(email="prem@test.com", password="Str0ng!Pass", role="premium")
    users, total = await service.list_users(role="premium")
    assert total == 1
    assert users[0].role == "premium"


@pytest.mark.asyncio
async def test_list_users_filter_by_active(service: UserService) -> None:
    await service.create_user(email="active@test.com", password="Str0ng!Pass", is_active=True)
    await service.create_user(email="inactive@test.com", password="Str0ng!Pass", is_active=False)
    users, total = await service.list_users(is_active=False)
    assert total == 1
    assert users[0].email == "inactive@test.com"


@pytest.mark.asyncio
async def test_update_user_changes_fields(service: UserService) -> None:
    user = await service.create_user(email="update@test.com", password="Str0ng!Pass")
    updated = await service.update_user(user.id, role="premium", is_verified=True)
    assert updated is not None
    assert updated.role == "premium"
    assert updated.is_verified is True


@pytest.mark.asyncio
async def test_update_user_email_conflict(service: UserService) -> None:
    await service.create_user(email="first@test.com", password="Str0ng!Pass")
    second = await service.create_user(email="second@test.com", password="Str0ng!Pass")
    with pytest.raises(ValueError, match="Email already in use"):
        await service.update_user(second.id, email="first@test.com")


@pytest.mark.asyncio
async def test_delete_user(service: UserService) -> None:
    user = await service.create_user(email="delete@test.com", password="Str0ng!Pass")
    assert await service.delete_user(user.id) is True
    assert await service.get_by_id(user.id) is None


@pytest.mark.asyncio
async def test_delete_missing_user(service: UserService) -> None:
    assert await service.delete_user(999) is False
