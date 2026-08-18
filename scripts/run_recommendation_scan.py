"""Populate live recommendations by running the AI scan service directly.

Usage (from repo root, with a configured .env / DATABASE_URL and network
access to the market-data provider):

    PYTHONPATH=src python scripts/run_recommendation_scan.py [--limit N] [--max-age-minutes M]

This performs the same work as ``POST /recommendations/scan`` on the API: it
loads the NSE universe (if needed) and scans every active symbol with the
selective 6-pillar ``AIRecommendationEngine``, storing only actionable
signals. NO-TRADE outcomes are skipped.
"""
import argparse
import asyncio
import sys

sys.path.insert(0, "src")

from titan_x.core.config import get_settings
from titan_x.db.session import create_engine, create_session_factory
from titan_x.services.recommendation_scan_service import (
    run_background_scan,
    run_universe_load,
)


async def main(limit: int | None, max_age_minutes: int | None) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    print("Loading NSE universe…")
    load = await run_universe_load(factory)
    print("  universe:", load)

    print("Running recommendation scan…")
    result = await run_background_scan(
        factory, max_age_minutes=max_age_minutes, limit=limit
    )
    print("Scan complete:")
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the AI recommendation scan")
    parser.add_argument("--limit", type=int, default=None, help="Max symbols to scan")
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=0,
        help="Rescan symbols older than N minutes (0 = rescan all)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.max_age_minutes))
