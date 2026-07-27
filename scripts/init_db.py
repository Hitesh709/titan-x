#!/usr/bin/env python
"""Initialize the database by creating all tables."""
import asyncio

from titan_x.core.config import get_settings
from titan_x.db.base import Base
from titan_x.db.session import create_engine
from titan_x.models import *  # noqa: F401, F403 - register all models


async def init_db() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    tables = list(Base.metadata.tables.keys())
    print(f"Created {len(tables)} tables:")
    for t in sorted(tables):
        print(f"  - {t}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())