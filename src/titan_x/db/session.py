from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Enable WAL + busy timeout on SQLite connections only."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


def _normalize_postgres_url(url: str) -> str:
    """Normalize Render/Neon PostgreSQL URLs for SQLAlchemy asyncpg."""
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]

    parts = urlsplit(url)
    if parts.scheme != "postgresql+asyncpg":
        return url

    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "channel_binding"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def create_engine(settings: Settings) -> AsyncEngine:
    url = settings.resolved_database_url
    connect_args: dict[str, object] = {}

    if url.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://")):
        url = _normalize_postgres_url(url)
        connect_args = {"statement_cache_size": 0}
    elif url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}

    engine = create_async_engine(
        url,
        echo=settings.sql_echo,
        connect_args=connect_args,
    )
    if url.startswith("sqlite"):
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
