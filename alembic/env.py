"""Alembic environment configuration for async SQLAlchemy.

Loads all models from titan_x.models so autogenerate detects schema changes.
Uses the application Settings for DATABASE_URL in both online and offline modes.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from titan_x.core.config import get_settings
from titan_x.db.base import Base

import titan_x.models  # noqa: F401 — register all models so autogenerate works

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def alembic_config_from_settings() -> dict[str, str]:
    """Build the alembic config dict using the application DATABASE_URL.

    The connection URL is injected at runtime so alembic.ini can remain
    checked in without secrets.
    """
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = str(settings.database_url)
    return cfg


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Renders SQL to stdout or to a file without connecting to the database.
    Useful for generating SQL that can be reviewed before applying.
    """
    url = str(settings.database_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute pending migrations against the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an engine from config and run migrations online."""
    cfg = alembic_config_from_settings()
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
