from collections.abc import AsyncIterator

from sqlalchemy import event, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from titan_x.core.config import Settings


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Enable WAL + busy timeout on every SQLite connection.

    The default rollback-journal mode blocks writers during long scans/ingestion
    and fails immediately on lock contention, surfacing as intermittent 500s on
    write endpoints (e.g. login). WAL allows concurrent readers + a single
    writer, and busy_timeout makes writers wait instead of erroring.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict = {}
    url = str(settings.database_url)
    # Render/managed Postgres hands over `postgres://` or `postgresql://`, but
    # SQLAlchemy's async engine needs the `postgresql+asyncpg://` driver.
    parsed = make_url(url)
    if parsed.get_backend_name() in ("postgres", "postgresql") and "asyncpg" not in (
        parsed.get_driver_name() or ""
    ):
        parsed = parsed.set(drivername="postgresql+asyncpg")
        url = str(parsed)
    if url.startswith("postgresql"):
        # Render Postgres requires TLS.  `ssl=require` in the URL is accepted
        # by asyncpg, but connect_args keeps this safe when the URL has no SSL
        # query parameter (for example a copied Render Internal URL).
        query = dict(parsed.query)
        if query.get("ssl") not in {"require", "verify-ca", "verify-full"}:
            connect_args["ssl"] = "require"
        connect_args["server_settings"] = {"application_name": settings.app_name}
    elif url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30

    kwargs: dict = dict(echo=settings.sql_echo, connect_args=connect_args or {})
    if not url.startswith("sqlite"):
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow

    engine = create_async_engine(url, **kwargs)
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
