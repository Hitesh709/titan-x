#!/usr/bin/env python
"""Initialize the database by creating all tables."""
import asyncio
import logging

from titan_x.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)
from titan_x.db.base import Base
from titan_x.db.session import create_engine
from titan_x.models import *  # noqa: F401, F403 - register all models


async def init_db() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    tables = list(Base.metadata.tables.keys())
    logger.info("Created %d tables:", len(tables))
    for t in sorted(tables):
        logger.info("  - %s", t)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())