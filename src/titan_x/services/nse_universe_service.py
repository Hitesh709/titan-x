"""Load the full NSE equity universe and persist exchange-specific listings."""
import csv
import io
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.company_listing import CompanyListing

logger = structlog.get_logger(__name__)

NSE_CSV_URLS = [
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
]
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"}


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
                except Exception as exc:
                    last_exc = exc
                    logger.warning("nse_csv_fetch_failed", url=url, error=str(exc))
            raise last_exc or RuntimeError("NSE equity list unreachable")

    @staticmethod
    def _parse(text: str) -> list[tuple[str, str, str]]:
        rows = []
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = {k: (k or "").strip() for k in reader.fieldnames or []}
        for raw in reader:
            row = {fieldnames.get(k, k): v for k, v in raw.items()}
            if (row.get("SERIES") or "").strip().upper() != "EQ":
                continue
            symbol = (row.get("SYMBOL") or "").strip().upper()
            name = (row.get("NAME OF COMPANY") or "").strip()
            isin = (row.get("ISIN NUMBER") or "").strip()
            if symbol:
                rows.append((symbol, name or symbol, isin))
        return rows

    async def load_universe(self) -> dict:
        source = "nse"
        try:
            universe = self._parse(await self._fetch_csv())
        except Exception as exc:
            logger.warning("nse_universe_unreachable_falling_back", error=str(exc))
            universe = self._fallback_universe()
            source = "fallback"
        return await self._upsert(universe, source)

    @staticmethod
    def _fallback_universe() -> list[tuple[str, str, str]]:
        from titan_x.core.seed_demo import COMPANIES
        return [(e[0], e[1], f"IN{e[0]}001") for e in COMPANIES if e[4] == "NSE" and e[0]]

    async def _upsert(self, universe: list[tuple[str, str, str]], source: str = "nse") -> dict:
        existing = (await self.session.execute(select(Company).where(Company.exchange == "NSE"))).scalars().all()
        by_symbol = {c.symbol: c for c in existing}
        added = kept = listings_added = listings_kept = 0
        now = datetime.now(timezone.utc)
        for symbol, name, isin in universe:
            if len(symbol) > 16:
                continue
            company = by_symbol.get(symbol)
            if company is None:
                # If an ISIN already belongs to a BSE company, attach the NSE listing to it.
                company = (await self.session.execute(select(Company).where(Company.isin == (isin or "")))).scalar_one_or_none() if isin else None
                if company is None:
                    company = Company(symbol=symbol, company_name=name, isin=isin or f"IN{symbol}001", sector="Equity", exchange="NSE", status="active", created_at=now, updated_at=now)
                    self.session.add(company)
                    await self.session.flush()
                    added += 1
                by_symbol[symbol] = company
            else:
                kept += 1
                company.company_name = name or company.company_name
                company.status = "active"
                company.updated_at = now
            listing = (await self.session.execute(select(CompanyListing).where(CompanyListing.exchange == "NSE", CompanyListing.symbol == symbol))).scalar_one_or_none()
            if listing is None:
                self.session.add(CompanyListing(company_id=company.id, exchange="NSE", symbol=symbol, yahoo_symbol=f"{symbol}.NS", is_active=True, created_at=now, updated_at=now))
                listings_added += 1
            else:
                listing.company_id = company.id
                listing.yahoo_symbol = f"{symbol}.NS"
                listing.is_active = True
                listing.updated_at = now
                listings_kept += 1
        await self.session.flush()
        total_active = await self._count_active()
        logger.info("nse_universe_loaded", source=source, total=len(universe), added=added, kept=kept, listings_added=listings_added, listings_kept=listings_kept)
        return {"source": source, "parsed": len(universe), "added": added, "kept": kept, "listings_added": listings_added, "listings_kept": listings_kept, "total_active": total_active}

    async def _count_active(self) -> int:
        result = await self.session.execute(select(func.count(Company.id)).where(Company.status == "active"))
        return result.scalar() or 0
