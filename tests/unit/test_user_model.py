from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.user import User


@pytest.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_creation(db: AsyncSession) -> None:
    user = User(
        email="user@example.com",
        hashed_password="hashed_secret",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    assert user.id is not None
    assert user.email == "user@example.com"
    assert user.hashed_password == "hashed_secret"
    assert user.is_active is True
    assert user.is_superuser is False
    assert user.is_verified is False
    assert user.role == "normal"
    assert isinstance(user.created_at, datetime)
    assert isinstance(user.updated_at, datetime)
    assert user.deleted_at is None
    assert user.is_deleted is False
