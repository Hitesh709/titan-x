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


def _normalize_postgres_url(url: str) -> tuple[str, dict[str, object]]:
    """Normalize PostgreSQL URLs for SQLAlchemy's asyncpg dialect.

    libpq-style ``sslmode`` and ``channel_binding`` parameters from Neon
    connection strings must not be passed as keyword arguments to asyncpg's
    SQLAlchemy adapter. Convert sslmode to asyncpg's ``ssl`` connect argument
    and remove channel_binding before SQLAlchemy creates the engine.
    """
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]

    parts = urlsplit(url)
    if parts.scheme != "postgresql+asyncpg":
        return url, {}

    connect_args: dict[str, object] = {"statement_cache_size": 0}
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.lower()
        if normalized_key == "sslmode":
            if value:
                connect_args["ssl"] = value
            continue
        if normalized_key == "channel_binding":
            continue
        query.append((key, value))

    clean_url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    return clean_url, connect_args


def create_engine(settings: Settings) -> AsyncEngine:
    url = settings.resolved_database_url
    connect_args: dict[str, object] = {}

    if url.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://")):
        url, connect_args = _normalize_postgres_url(url)
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
