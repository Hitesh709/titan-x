import asyncio
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.company import Company
from titan_x.models.news import NewsArticle
from titan_x.models.professional_report import ProfessionalReport
from titan_x.models.sector import SectorPerformance
from titan_x.models.strategy import Strategy

logger = structlog.get_logger(__name__)


class GlobalSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self, query: str, user_id: int, limit: int = 10
    ) -> dict[str, list[dict[str, Any]]]:
        if not query or not query.strip():
            empty = {
                k: [] for k in ("companies", "symbols", "sectors", "reports", "strategies", "news")
            }
            empty["total_results"] = 0
            return empty
        q = query.strip()

        companies_task = self._search_companies(q, limit)
        symbols_task = self._search_symbols(q, limit)
        sectors_task = self._search_sectors(q, limit)
        reports_task = self._search_reports(q, limit)
        strategies_task = self._search_strategies(q, user_id, limit)
        news_task = self._search_news(q, limit)

        companies, symbols, sectors, reports, strategies, news = await asyncio.gather(
            companies_task,
            symbols_task,
            sectors_task,
            reports_task,
            strategies_task,
            news_task,
        )

        return {
            "companies": companies,
            "symbols": symbols,
            "sectors": sectors,
            "reports": reports,
            "strategies": strategies,
            "news": news,
            "total_results": (
                len(companies)
                + len(symbols)
                + len(sectors)
                + len(reports)
                + len(strategies)
                + len(news)
            ),
        }

    async def _search_companies(self, q: str, limit: int) -> list[dict[str, Any]]:
        stmt = (
            select(Company)
            .where(
                or_(
                    Company.company_name.ilike(f"%{q}%"),
                    Company.symbol.ilike(f"%{q}%"),
                    Company.sector.ilike(f"%{q}%"),
                    Company.industry.ilike(f"%{q}%"),
                    Company.description.ilike(f"%{q}%"),
                )
            )
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "id": c.id,
                "symbol": c.symbol,
                "company_name": c.company_name,
                "sector": c.sector,
                "industry": c.industry,
                "exchange": c.exchange,
                "market_cap": c.market_cap,
            }
            for c in rows
        ]

    async def _search_symbols(self, q: str, limit: int) -> list[dict[str, Any]]:
        stmt = select(Company).where(Company.symbol.ilike(f"%{q}%")).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        if rows:
            return [
                {
                    "id": c.id,
                    "symbol": c.symbol,
                    "company_name": c.company_name,
                    "exchange": c.exchange,
                    "sector": c.sector,
                }
                for c in rows
            ]
        if not await self._companies_table_empty():
            return []
        return await self._search_symbols_remote(q, limit)

    async def _companies_table_empty(self) -> bool:
        result = await self._session.execute(select(func.count(Company.id)))
        return (result.scalar() or 0) == 0

    async def _search_symbols_remote(self, q: str, limit: int) -> list[dict[str, Any]]:
        """Fallback to a live provider search when the local companies table
        yields no Symbol match (e.g. a fresh database before the universe has
        been seeded). Never blocks on provider failure."""
        try:
            provider = get_market_data_provider(get_settings().market_data_provider)
        except Exception:  # noqa: BLE001
            return []
        try:
            results = await provider.search_symbols(q, limit=limit)
        except Exception:  # noqa: BLE001
            return []
        return [
            {
                "id": None,
                "symbol": r["symbol"],
                "company_name": r.get("company_name") or r["symbol"],
                "exchange": r.get("exchange") or "NSE",
                "sector": r.get("sector"),
                "source": r.get("source", "yahoo"),
            }
            for r in results
        ]

    async def _search_sectors(self, q: str, limit: int) -> list[dict[str, Any]]:
        distinct_sectors = (
            select(SectorPerformance.sector)
            .where(SectorPerformance.sector.ilike(f"%{q}%"))
            .distinct()
            .limit(limit)
        )
        rows = (await self._session.execute(distinct_sectors)).scalars().all()
        enriched = []
        for sector_name in rows:
            latest = (
                await self._session.execute(
                    select(SectorPerformance)
                    .where(SectorPerformance.sector == sector_name)
                    .order_by(SectorPerformance.as_of_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            enriched.append(
                {
                    "sector": sector_name,
                    "latest_return_pct": latest.return_pct if latest else None,
                    "latest_momentum_score": latest.momentum_score if latest else None,
                    "as_of_date": (
                        latest.as_of_date.isoformat() if latest and latest.as_of_date else None
                    ),
                }
            )
        return enriched

    async def _search_reports(self, q: str, limit: int) -> list[dict[str, Any]]:
        stmt = (
            select(ProfessionalReport)
            .where(
                or_(
                    ProfessionalReport.symbol.ilike(f"%{q}%"),
                    ProfessionalReport.direction.ilike(f"%{q}%"),
                )
            )
            .order_by(ProfessionalReport.trade_date.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "trade_date": r.trade_date.isoformat() if r.trade_date else None,
                "direction": r.direction,
                "current_price": r.current_price,
            }
            for r in rows
        ]

    async def _search_strategies(self, q: str, user_id: int, limit: int) -> list[dict[str, Any]]:
        stmt = (
            select(Strategy)
            .where(
                Strategy.user_id == user_id,
                or_(
                    Strategy.name.ilike(f"%{q}%"),
                    Strategy.description.ilike(f"%{q}%"),
                ),
            )
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "is_active": s.is_active,
                "is_public": s.is_public,
                "version": s.version,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            }
            for s in rows
        ]

    async def _search_news(self, q: str, limit: int) -> list[dict[str, Any]]:
        stmt = (
            select(NewsArticle)
            .where(
                or_(
                    NewsArticle.title.ilike(f"%{q}%"),
                    NewsArticle.summary.ilike(f"%{q}%"),
                    NewsArticle.symbol.ilike(f"%{q}%"),
                )
            )
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "id": a.id,
                "title": a.title,
                "summary": a.summary[:300] if a.summary else None,
                "symbol": a.symbol,
                "source": a.source,
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in rows
        ]
