"""Load the full NSE equity universe into the companies table.

Downloads the official NSE equities master list (EQUITY_L.csv) and upserts every
``EQ`` series symbol. Falls back to the seeded demo universe when the NSE
archive is unreachable so startup never depends on the network.
"""
import csv
import io
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company

logger = structlog.get_logger(__name__)

NSE_CSV_URLS = [
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
]
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


class NSEUniverseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    async def _fetch_csv() -> str:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0, follow_redirects=True) as client:
            last_exc: Exception | None = None
            for url in NSE_CSV_URLS:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.text
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.warning("nse_csv_fetch_failed", url=url, error=str(exc))
            raise last_exc or RuntimeError("NSE equity list unreachable")

    @staticmethod
    def _parse(text: str) -> list[tuple[str, str, str]]:
        """Return (symbol, name, isin) rows filtered to the EQ series."""
        rows: list[tuple[str, str, str]] = []
        reader = csv.DictReader(io.StringIO(text))
        # NSE headers have leading spaces (" SERIES", " ISIN NUMBER").
        fieldnames = {k: (k or "").strip() for k in reader.fieldnames or []}
        for raw in reader:
            row = {fieldnames.get(k, k): v for k, v in raw.items()}
            series = (row.get("SERIES") or "").strip().upper()
            symbol = (row.get("SYMBOL") or "").strip().upper()
            name = (row.get("NAME OF COMPANY") or "").strip()
            isin = (row.get("ISIN NUMBER") or "").strip()
            if series != "EQ" or not symbol:
                continue
            rows.append((symbol, name or symbol, isin))
        return rows

    async def load_universe(self) -> dict:
        source = "nse"
        try:
            universe = self._parse(await self._fetch_csv())
        except Exception as exc:  # noqa: BLE001
            logger.warning("nse_universe_unreachable_falling_back", error=str(exc))
            universe = self._fallback_universe()
            source = "fallback"
        return await self._upsert(universe, source=source)

    @staticmethod
    def _fallback_universe() -> list[tuple[str, str, str]]:
        """Curated NSE universe used when the official CSV is unreachable so
        the companies table is never empty and search keeps working."""
        from titan_x.core.seed_demo import COMPANIES

        rows: list[tuple[str, str, str]] = []
        for entry in COMPANIES:
            symbol, name, _sector, _industry, exchange, *_ = entry
            if exchange == "NSE" and symbol:
                rows.append((symbol, name, f"IN{symbol}001"))
        if not rows:
            raise RuntimeError("NSE equity list unreachable and no fallback universe available")
        return rows

    async def _upsert(self, universe: list[tuple[str, str, str]], source: str = "nse") -> dict:
        existing = await self.session.execute(
            select(Company.symbol).where(Company.exchange == "NSE")
        )
        known = {r[0] for r in existing.all()}

        added = 0
        kept = 0
        now = datetime.now(timezone.utc)
        for symbol, name, isin in universe:
            if len(symbol) > 16:
                continue
            if symbol in known:
                kept += 1
                continue
            self.session.add(Company(
                symbol=symbol,
                company_name=name,
                isin=isin or f"IN{symbol}001",
                sector="Equity",
                exchange="NSE",
                status="active",
                created_at=now,
                updated_at=now,
            ))
            known.add(symbol)
            added += 1

        await self.session.flush()
        logger.info("nse_universe_loaded", source=source, total=len(universe), added=added, kept=kept)
        return {
            "source": source,
            "parsed": len(universe),
            "added": added,
            "kept": kept,
            "total_active": await self._count_active(),
        }

    async def _count_active(self) -> int:
        result = await self.session.execute(
            select(func.count(Company.id)).where(Company.status == "active")
        )
        return result.scalar() or 0