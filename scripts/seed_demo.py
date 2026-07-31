#!/usr/bin/env python
"""Seed the TITAN X database with realistic demo market data and a demo user.

Populates:
  - Companies, ~260 days of daily prices, sector performance, market breadth
  - A demo user (demo@titanx.app / Demo1234!) with a paper account, positions,
    watchlists, AI scores, news articles and monitor events

Run once against an empty DB:
    python scripts/seed_demo.py
The script is idempotent: re-running it replaces the seeded rows.
"""
import asyncio

from titan_x.core.config import get_settings
from titan_x.core.seed_demo import seed_all
from titan_x.db.base import Base
from titan_x.db.session import create_engine, create_session_factory
from titan_x.models import *  # noqa: F401, F403 - register all models


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    try:
        await seed_all(session_factory)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
