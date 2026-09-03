"""Alembic environment configuration for async SQLAlchemy."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from titan_x.core.config import get_settings
from titan_x.db.base import Base

import titan_x.models  # noqa: F401

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def normalized_database_url() -> str:
    """Normalize Render/PostgreSQL URLs exactly like the runtime engine."""
    raw = str(settings.database_url)
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+asyncpg"
    elif scheme == "postgresql+asyncpg":
        scheme = "postgresql+asyncpg"
    else:
        return raw

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "ssl" not in query:
        query["ssl"] = "require"
    return urlunsplit((scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def alembic_config_from_settings() -> dict[str, str]:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = normalized_database_url()
    return cfg


def run_migrations_offline() -> None:
    context.configure(
        url=normalized_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = alembic_config_from_settings()
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"application_name": settings.app_name}},
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
