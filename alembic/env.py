"""Alembic environment configuration for async SQLAlchemy."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection, make_url
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
    """Normalize the configured database URL for the async SQLAlchemy driver."""
    raw = settings.resolved_database_url
    parsed = make_url(raw)
    if parsed.get_backend_name() == "mysql" and not parsed.get_driver_name():
        parsed = parsed.set(drivername="mysql+aiomysql")
    return str(parsed)


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
