from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict = {}
    url = str(settings.database_url)
    if url.startswith("postgresql"):
        connect_args["server_settings"] = {"application_name": settings.app_name}
    elif url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    kwargs: dict = dict(echo=settings.sql_echo, connect_args=connect_args or {})
    if not url.startswith("sqlite"):
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow

    return create_async_engine(url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
