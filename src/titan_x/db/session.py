from collections.abc import AsyncIterator

from sqlalchemy import event, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Enable WAL + busy timeout on every SQLite connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict = {}
    url = settings.resolved_database_url
    parsed = make_url(url)

    # Keep SQLite support for local development/tests. Production Titan X uses
    # MySQL with the asyncmy-compatible aiomysql SQLAlchemy driver.
    if parsed.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30
    elif parsed.get_backend_name() == "mysql" and not parsed.get_driver_name():
        parsed = parsed.set(drivername="mysql+aiomysql")
        url = str(parsed)

    kwargs: dict = dict(echo=settings.sql_echo, connect_args=connect_args or {})
    if parsed.get_backend_name() != "sqlite":
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow

    engine = create_async_engine(url, **kwargs)
    if parsed.get_backend_name() == "sqlite":
        event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
    return engine


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
