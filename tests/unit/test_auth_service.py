import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings
from titan_x.core.security import hash_password
from titan_x.db.base import Base
from titan_x.models.user import User
from titan_x.services.auth_service import AuthService

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
async def service(session: AsyncSession) -> AuthService:
    return AuthService(session, _settings)


@pytest.mark.asyncio
async def test_register_creates_user(service: AuthService) -> None:
    user = await service.register(email="new@test.com", password="Str0ng!Pass")
    assert user.id is not None
    assert user.email == "new@test.com"
    assert not user.is_verified


@pytest.mark.asyncio
async def test_register_duplicate_email_raises(service: AuthService) -> None:
    await service.register(email="dup@test.com", password="Str0ng!Pass")
    with pytest.raises(ValueError, match="Email already registered"):
        await service.register(email="dup@test.com", password="Other!1")


@pytest.mark.asyncio
async def test_login_returns_user_and_tokens(service: AuthService) -> None:
    await service.register(email="log@test.com", password="Str0ng!Pass")
    user, access, refresh, jti = await service.login(email="log@test.com", password="Str0ng!Pass")
    assert user.email == "log@test.com"
    assert isinstance(access, str) and access.startswith("ey")
    assert isinstance(refresh, str) and refresh.startswith("ey")
    assert isinstance(jti, str) and len(jti) > 16


@pytest.mark.asyncio
async def test_login_invalid_password_raises(service: AuthService) -> None:
    await service.register(email="fail@test.com", password="Str0ng!Pass")
    with pytest.raises(ValueError, match="Invalid email or password"):
        await service.login(email="fail@test.com", password="wrong")


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(service: AuthService) -> None:
    await service.register(email="ref@test.com", password="Str0ng!Pass")
    _, _, refresh, jti = await service.login(email="ref@test.com", password="Str0ng!Pass")
    new_access, new_refresh, new_jti = await service.refresh(jti, 1)
    assert isinstance(new_access, str) and new_access.startswith("ey")
    assert isinstance(new_refresh, str) and new_refresh.startswith("ey")
    assert new_jti != jti


@pytest.mark.asyncio
async def test_logout_revokes_token(service: AuthService) -> None:
    await service.register(email="lo@test.com", password="Str0ng!Pass")
    _, _, _, jti = await service.login(email="lo@test.com", password="Str0ng!Pass")
    await service.logout(jti, 1)
    with pytest.raises(ValueError, match="Invalid or revoked refresh token"):
        await service.refresh(jti, 1)


@pytest.mark.asyncio
async def test_forgot_password_returns_token_for_existing_user(service: AuthService) -> None:
    await service.register(email="fp@test.com", password="Str0ng!Pass")
    token = await service.forgot_password(email="fp@test.com")
    assert token is not None
    assert isinstance(token, str) and token.startswith("ey")


@pytest.mark.asyncio
async def test_forgot_password_returns_none_for_missing_user(service: AuthService) -> None:
    token = await service.forgot_password(email="nonexistent@test.com")
    assert token is None


@pytest.mark.asyncio
async def test_reset_password_changes_password(service: AuthService) -> None:
    await service.register(email="rp@test.com", password="OldPass!1")
    token = await service.forgot_password(email="rp@test.com")
    assert token is not None
    await service.reset_password(token=token, new_password="NewPass!2")
    user, _, _, _ = await service.login(email="rp@test.com", password="NewPass!2")
    assert user.email == "rp@test.com"
    with pytest.raises(ValueError, match="Invalid email or password"):
        await service.login(email="rp@test.com", password="OldPass!1")
