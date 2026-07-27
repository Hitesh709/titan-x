import hashlib
import re
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.db.repository import BaseRepository
from titan_x.models.news import NewsArticle, NewsArticleCategory, NewsCategory

logger = structlog.get_logger(__name__)

BUILTIN_CATEGORIES: dict[str, str] = {
    "earnings": "Earnings reports and financial results",
    "mergers_and_acquisitions": "Mergers, acquisitions, and takeovers",
    "markets": "Market commentary and analysis",
    "economy": "Macroeconomic news and indicators",
    "regulation": "Regulatory and compliance news",
    "corporate_actions": "Dividends, buybacks, splits, and rights issues",
    "industry": "Industry-specific news and trends",
    "technology": "Technology and innovation news",
    "ipo": "Initial public offerings and listings",
    "esg": "Environmental, social, and governance topics",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "earnings": ["earnings", "revenue", "profit", "net income", "quarterly result", "fiscal", "guidance"],
    "mergers_and_acquisitions": ["merger", "acquisition", "takeover", "buyout", "acquire", "merge"],
    "markets": ["market", "index", "rally", "decline", "volatility", "bull", "bear"],
    "economy": ["gdp", "inflation", "unemployment", "interest rate", "central bank", "fed", "treasury"],
    "regulation": ["sec", "regulatory", "compliance", "regulation", "fine", "investigation"],
    "corporate_actions": ["dividend", "buyback", "stock split", "rights issue", "share repurchase"],
    "industry": ["sector", "industry", "supply chain", "manufacturing"],
    "technology": ["ai", "artificial intelligence", "cloud", "software", "tech", "digital"],
    "ipo": ["ipo", "initial public offering", "listing", "spin-off"],
    "esg": ["esg", "sustainable", "carbon", "net zero", "green", "climate"],
}


class InvalidArticleError(ValueError):
    pass


class NewsCleaningService:
    @staticmethod
    def strip_html(text: str | None) -> str | None:
        if text is None:
            return None
        return re.sub(r"<[^>]+>", "", text)

    @staticmethod
    def normalize_whitespace(text: str | None) -> str | None:
        if text is None:
            return None
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def truncate(text: str | None, max_len: int = 10000) -> str | None:
        if text is None:
            return None
        return text[:max_len] if len(text) > max_len else text

    @staticmethod
    def clean_text(text: str | None) -> str | None:
        text = NewsCleaningService.strip_html(text)
        text = NewsCleaningService.normalize_whitespace(text)
        text = NewsCleaningService.truncate(text)
        return text


class NewsDeduplicationService:
    @staticmethod
    def compute_url_hash(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_fingerprint(title: str, content: str | None) -> str:
        raw = (title or "") + "|" + (content or "")
        normalized = re.sub(r"\s+", " ", raw).strip().lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()


class NewsCategorizationService:
    def __init__(self) -> None:
        self._keyword_map = CATEGORY_KEYWORDS

    def categorize(self, title: str, content: str | None) -> list[str]:
        text = (title or "") + " " + (content or "")
        text = text.lower()
        matched: list[str] = []
        for category, keywords in self._keyword_map.items():
            for kw in keywords:
                if kw in text:
                    matched.append(category)
                    break
        if not matched:
            matched.append("markets")
        return matched


class NewsSourceConnector:
    @staticmethod
    def validate_article(article: dict[str, Any]) -> None:
        if not article.get("title") and not article.get("source_id"):
            raise InvalidArticleError("Article must have a title or source_id")
        if not article.get("url"):
            raise InvalidArticleError("Article must have a url")

    @staticmethod
    def normalize(article: dict[str, Any], source: str) -> dict[str, Any]:
        return {
            "title": str(article.get("title", "")).strip(),
            "summary": str(article.get("summary") or article.get("description") or "").strip() or None,
            "content": str(article.get("content") or "").strip() or None,
            "source": source,
            "source_id": str(article.get("source_id", article.get("id", article.get("url", "")))),
            "url": article["url"],
            "symbol": str(article.get("symbol") or "").upper().strip() or None,
            "author": str(article.get("author") or "").strip() or None,
            "published_at": article.get("published_at") or article.get("publishedAt") or None,
            "language": str(article.get("language") or "en").lower()[:8],
        }


class NewsEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._article_repo = BaseRepository(session, NewsArticle)
        self._category_repo = BaseRepository(session, NewsCategory)
        self._cleaning = NewsCleaningService()
        self._dedup = NewsDeduplicationService()
        self._categorization = NewsCategorizationService()

    async def _ensure_categories(self) -> dict[str, NewsCategory]:
        cat_map: dict[str, NewsCategory] = {}
        for name, desc in BUILTIN_CATEGORIES.items():
            result = await self._session.execute(
                select(NewsCategory).where(NewsCategory.name == name)
            )
            cat = result.scalar_one_or_none()
            if cat is None:
                cat = await self._category_repo.create(name=name, description=desc)
            cat_map[name] = cat
        return cat_map

    async def ingest(self, source: str, raw_articles: list[dict[str, Any]], *, run_nlp: bool = True) -> dict[str, Any]:
        source = source.lower().strip()
        stats: dict[str, Any] = {"total": len(raw_articles), "created": 0, "duplicates": 0, "errors": 0, "errors_detail": []}
        nlp_engine: Any = None
        cat_map = await self._ensure_categories()

        for raw in raw_articles:
            try:
                NewsSourceConnector.validate_article(raw)
                normalized = NewsSourceConnector.normalize(raw, source)

                url_hash = self._dedup.compute_url_hash(normalized["url"])

                existing = await self._session.execute(
                    select(NewsArticle).where(
                        or_(
                            and_(
                                NewsArticle.source == source,
                                NewsArticle.source_id == normalized["source_id"],
                            ),
                            NewsArticle.url_hash == url_hash,
                        )
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    stats["duplicates"] += 1
                    continue

                clean_content = self._cleaning.clean_text(normalized["content"])
                clean_summary = self._cleaning.clean_text(normalized["summary"])
                clean_title = self._cleaning.normalize_whitespace(normalized["title"]) or ""

                fingerprint = self._dedup.compute_fingerprint(clean_title, clean_content)

                fp_dup = await self._session.execute(
                    select(NewsArticle).where(NewsArticle.fingerprint == fingerprint)
                )
                if fp_dup.scalar_one_or_none() is not None:
                    stats["duplicates"] += 1
                    continue

                categories = self._categorization.categorize(clean_title, clean_content)

                article = await self._article_repo.create(
                    title=clean_title,
                    summary=clean_summary,
                    content=clean_content,
                    source=source,
                    source_id=normalized["source_id"],
                    url=normalized["url"],
                    url_hash=url_hash,
                    symbol=normalized.get("symbol"),
                    author=normalized.get("author"),
                    published_at=normalized.get("published_at"),
                    language=normalized.get("language", "en"),
                    is_cleaned=True,
                    fingerprint=fingerprint,
                )

                for cat_name in categories:
                    category = cat_map.get(cat_name)
                    if category:
                        link = NewsArticleCategory(article_id=article.id, category_id=category.id)
                        self._session.add(link)

                if run_nlp:
                    if nlp_engine is None:
                        from titan_x.services.news_nlp import NewsNLPEngine
                        nlp_engine = NewsNLPEngine(self._session)
                    try:
                        await nlp_engine.process_article(article.id)
                    except Exception as exc:
                        logger.warning("nlp_ingest_error", article_id=article.id, error=str(exc))

                stats["created"] += 1
            except InvalidArticleError as exc:
                stats["errors"] += 1
                stats["errors_detail"].append(str(exc))
            except Exception as exc:
                stats["errors"] += 1
                stats["errors_detail"].append(str(exc))
                logger.warning("ingest_error", source=source, error=str(exc))

        await self._session.flush()
        logger.info("ingest_complete", source=source, **{k: v for k, v in stats.items() if k != "errors_detail"})
        return stats

    async def search(
        self, *, query: str | None = None, symbol: str | None = None,
        source: str | None = None, category: str | None = None,
        date_from: date | None = None, date_to: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[NewsArticle], int]:
        stmt = select(NewsArticle)

        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    NewsArticle.title.ilike(pattern),
                    NewsArticle.summary.ilike(pattern),
                    NewsArticle.content.ilike(pattern),
                )
            )
        if symbol:
            stmt = stmt.where(NewsArticle.symbol == symbol.upper())
        if source:
            stmt = stmt.where(NewsArticle.source == source.lower().strip())
        if date_from:
            stmt = stmt.where(NewsArticle.published_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            stmt = stmt.where(NewsArticle.published_at <= datetime.combine(date_to, datetime.max.time()))
        if category:
            stmt = stmt.join(NewsArticleCategory).join(NewsCategory).where(NewsCategory.name == category)

        count_stmt = stmt
        total_result = await self._session.execute(count_stmt)
        total = len(total_result.scalars().all())

        stmt = stmt.order_by(NewsArticle.published_at.desc().nullslast()).offset(skip).limit(limit)
        stmt = stmt.options(selectinload(NewsArticle.categories))
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_by_id(self, article_id: int) -> NewsArticle | None:
        result = await self._session.execute(
            select(NewsArticle)
            .where(NewsArticle.id == article_id)
            .options(selectinload(NewsArticle.categories))
        )
        return result.scalar_one_or_none()

    async def list_sources(self) -> list[str]:
        result = await self._session.execute(
            select(NewsArticle.source).distinct().order_by(NewsArticle.source)
        )
        return list(result.scalars().all())

    async def list_categories(self) -> list[NewsCategory]:
        result = await self._session.execute(
            select(NewsCategory).order_by(NewsCategory.name)
        )
        return list(result.scalars().all())

    async def delete_article(self, article_id: int) -> bool:
        return await self._article_repo.delete(article_id)

    async def get_stats(self) -> dict[str, Any]:
        total_result = await self._session.execute(select(func.count(NewsArticle.id)))
        total = total_result.scalar() or 0
        source_result = await self._session.execute(
            select(NewsArticle.source, func.count(NewsArticle.id))
            .group_by(NewsArticle.source)
        )
        per_source = dict(source_result.all())
        return {"total_articles": total, "per_source": per_source}
