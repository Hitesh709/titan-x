#!/usr/bin/env python
"""
Complete Market Data Rebuild for TITAN X.

Wipes ALL market data (prices, indices, sectors, breadth, companies,
recommendations) and rebuilds everything from scratch using the same
seed pipeline as the app (real Yahoo data with deterministic synthetic
fallback), then runs a full recommendation scan.

Run on Render Shell (env vars are already set there):
    python scripts/rebuild_market_data.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import structlog

from titan_x.core.config import get_settings  # noqa: F401 - validates env
from titan_x.core.seed_demo import seed_all
from titan_x.db.base import Base
from titan_x.db.session import create_engine, create_session_factory
from titan_x.models import *  # noqa: F401, F403 - register all models
from titan_x.services.recommendation_scan_service import RecommendationScanService

logger = structlog.get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    await _create_tables(engine)
    session_factory = create_session_factory(engine)

    logger.info("=== STEP 1/3: wipe + reseed all market data ===")
    await seed_all(session_factory)

    logger.info("=== STEP 2/3: run full recommendation scan ===")
    async with session_factory() as session:
        svc = RecommendationScanService(session)
        result = await svc.scan_all(max_age_minutes=0, limit=500)
        logger.info(
            "scan_complete",
            universe=result.get("universe"),
            scanned=result.get("scanned"),
            stored=result.get("stored"),
            no_trade=result.get("no_trade"),
            insufficient=result.get("insufficient_data"),
            failed=result.get("failed"),
        )

    logger.info("=== STEP 3/3: verify row counts ===")
    from sqlalchemy import func, select

    from titan_x.models.company import Company
    from titan_x.models.price import DailyPrice
    from titan_x.models.recommendation import Recommendation

    async with session_factory() as session:
        companies = (await session.execute(select(func.count(Company.id)))).scalar()
        prices = (await session.execute(select(func.count(DailyPrice.id)))).scalar()
        recs = (await session.execute(select(func.count(Recommendation.id)))).scalar()
        logger.info("row_counts", companies=companies, daily_prices=prices, recommendations=recs)

    await engine.dispose()
    logger.info("=== REBUILD COMPLETE ===")


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(main())
