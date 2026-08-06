"""News Scanner service.

Scans news articles across five dimensions — Company, Sector, Macro,
Government, and Global — and generates AI tags from existing NLP analysis data.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from titan_x.core.time import utcnow
from typing import Any

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.models.company import Company
from titan_x.models.news import NewsArticle, NewsArticleCategory, NewsCategory
from titan_x.models.news_nlp import NewsEntity, NewsNLPAnalysis

logger = structlog.get_logger(__name__)


class NewsScannerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def scan(
        self, days: int = 7, min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        cutoff = utcnow() - timedelta(days=days)
        articles = await self._load_articles(cutoff)
        results: dict[str, Any] = {
            "scan_date": date.today().isoformat(),
            "lookback_days": days,
            "total_articles": len(articles),
            "categories": {},
        }

        by_category = self._categorize(articles)
        for cat_name in ["company", "sector", "macro", "government", "global"]:
            cat_articles = by_category.get(cat_name, [])
            results["categories"][cat_name] = self._scan_category(cat_name, cat_articles)

        results["category_counts"] = {
            cat: len(by_category.get(cat, [])) for cat in ["company", "sector", "macro", "government", "global"]
        }
        return results

    async def scan_category(
        self, category: str, days: int = 7, min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        cutoff = utcnow() - timedelta(days=days)
        articles = await self._load_articles(cutoff)
        by_category = self._categorize(articles)
        cat_articles = by_category.get(category, [])
        return self._scan_category(category, cat_articles)

    def _scan_category(
        self, cat_name: str, articles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not articles:
            return {
                "article_count": 0, "dominant_sentiment": "neutral",
                "avg_confidence": 0.0, "tags": [],
                "top_entities": [], "top_events": [], "top_sectors": [],
                "top_symbols": [], "articles": [],
            }

        sentiments = [a["sentiment_label"] for a in articles if a["sentiment_label"]]
        sentiment_counts = Counter(sentiments)
        dominant = sentiment_counts.most_common(1)[0][0] if sentiment_counts else "neutral"

        confidences = [a["overall_confidence"] for a in articles if a["overall_confidence"] is not None]
        avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

        all_entities: list[str] = []
        all_events: list[str] = []
        all_sectors: list[str] = []
        all_symbols: list[str] = []
        all_keywords: list[str] = []

        for a in articles:
            all_entities.extend(a.get("entities", []))
            all_events.extend(a.get("events", []))
            if a.get("mapped_sector"):
                all_sectors.append(a["mapped_sector"])
            if a.get("symbol"):
                all_symbols.append(a["symbol"])
            all_keywords.extend(self._extract_keywords(a["title"]))

        entity_counts = Counter(all_entities)
        event_counts = Counter(all_events)
        sector_counts = Counter(all_sectors)
        symbol_counts = Counter(all_symbols)
        keyword_counts = Counter(all_keywords)

        tags = self._generate_tags(
            cat_name, dominant, avg_conf, sentiment_counts,
            entity_counts, event_counts, sector_counts, symbol_counts,
            keyword_counts, len(articles),
        )

        return {
            "article_count": len(articles),
            "dominant_sentiment": dominant,
            "sentiment_distribution": dict(sentiment_counts),
            "avg_confidence": avg_conf,
            "tags": tags,
            "top_entities": [{"text": e, "count": c} for e, c in entity_counts.most_common(10)],
            "top_events": [{"event": e, "count": c} for e, c in event_counts.most_common(10)],
            "top_sectors": [{"sector": s, "count": c} for s, c in sector_counts.most_common(10)],
            "top_symbols": [{"symbol": s, "count": c} for s, c in symbol_counts.most_common(10)],
            "articles": [
                {
                    "id": a["id"], "title": a["title"], "symbol": a["symbol"],
                    "sentiment": a["sentiment_label"], "confidence": a["overall_confidence"],
                    "published_at": a["published_at"].isoformat() if a.get("published_at") else None,
                }
                for a in sorted(articles, key=lambda x: x.get("published_at") or datetime.min, reverse=True)[:20]
            ],
        }

    def _generate_tags(
        self, cat_name: str, dominant: str, avg_conf: float,
        sentiment_counts: Counter, entity_counts: Counter,
        event_counts: Counter, sector_counts: Counter,
        symbol_counts: Counter, keyword_counts: Counter,
        article_count: int,
    ) -> list[dict[str, Any]]:
        tags: list[dict[str, Any]] = []
        if dominant == "positive":
            tags.append({"tag": "bullish_sentiment", "label": "Bullish Sentiment", "confidence": avg_conf, "count": sentiment_counts.get("positive", 0)})
        elif dominant == "negative":
            tags.append({"tag": "bearish_sentiment", "label": "Bearish Sentiment", "confidence": avg_conf, "count": sentiment_counts.get("negative", 0)})
        else:
            tags.append({"tag": "neutral_sentiment", "label": "Neutral Sentiment", "confidence": avg_conf, "count": sentiment_counts.get("neutral", 0)})

        for event, count in event_counts.most_common(5):
            tags.append({"tag": f"event:{event}", "label": event.replace("_", " ").title(), "confidence": round(count / max(article_count, 1), 2), "count": count})

        for sector, count in sector_counts.most_common(3):
            tags.append({"tag": f"sector:{sector}", "label": sector.replace("_", " ").title(), "confidence": round(count / max(article_count, 1), 2), "count": count})

        for symbol, count in symbol_counts.most_common(5):
            tags.append({"tag": f"symbol:{symbol}", "label": f"${symbol}", "confidence": round(count / max(article_count, 1), 2), "count": count})

        top_keywords = keyword_counts.most_common(5)
        for kw, count in top_keywords:
            tags.append({"tag": f"keyword:{kw}", "label": kw.title(), "confidence": round(count / max(article_count, 1), 2), "count": count})

        if avg_conf >= 0.6:
            tags.append({"tag": "high_confidence", "label": "High Confidence Signals", "confidence": avg_conf, "count": article_count})
        elif avg_conf >= 0.3:
            tags.append({"tag": "moderate_confidence", "label": "Moderate Confidence", "confidence": avg_conf, "count": article_count})
        else:
            tags.append({"tag": "low_confidence", "label": "Low Confidence", "confidence": avg_conf, "count": article_count})

        return tags

    async def _load_articles(
        self, cutoff: datetime,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(NewsArticle)
            .outerjoin(NewsNLPAnalysis)
            .options(
                selectinload(NewsArticle.nlp_analysis),
                selectinload(NewsArticle.entities),
                selectinload(NewsArticle.categories),
            )
            .where(
                or_(
                    NewsArticle.published_at >= cutoff,
                    NewsArticle.published_at.is_(None),
                )
            )
            .order_by(NewsArticle.published_at.desc().nullslast())
        )
        result = await self.session.execute(stmt)
        articles = list(result.scalars().all())

        return [self._article_dict(a) for a in articles]

    def _article_dict(self, a: NewsArticle) -> dict[str, Any]:
        nlp = a.nlp_analysis
        entities = [e.entity_text for e in a.entities if e.entity_type in ("ORGANIZATION", "TICKER")]
        events = []
        if nlp and nlp.detected_events:
            try:
                event_list = json.loads(nlp.detected_events)
                events = [e.get("event_type", "") for e in event_list if e.get("event_type")]
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": a.id,
            "title": a.title or "",
            "symbol": a.symbol,
            "published_at": a.published_at,
            "sentiment_label": nlp.sentiment_label if nlp else None,
            "overall_confidence": nlp.overall_confidence if nlp else None,
            "mapped_sector": nlp.mapped_sector if nlp else None,
            "entities": entities,
            "events": events,
            "categories": [c.name for c in a.categories],
        }

    def _categorize(
        self, articles: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        by_category: dict[str, list[dict[str, Any]]] = {
            "company": [], "sector": [], "macro": [],
            "government": [], "global": [],
        }
        for a in articles:
            cats = a.get("categories", [])
            if a.get("symbol"):
                by_category["company"].append(a)
            if a.get("mapped_sector"):
                by_category["sector"].append(a)
            if any(c in ("economy",) for c in cats):
                by_category["macro"].append(a)
            if any(c in ("regulation",) for c in cats):
                by_category["government"].append(a)
            if any(c in ("markets", "industry") for c in cats) or a.get("symbol") is None:
                by_category["global"].append(a)
        return by_category

    def _extract_keywords(self, title: str) -> list[str]:
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "out", "off", "over", "under", "again",
            "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only",
            "own", "same", "so", "than", "too", "very", "just", "because",
            "and", "but", "or", "if", "while", "that", "this", "these",
            "those", "it", "its", "new", "after", "up", "down",
        }
        words = title.lower().split()
        return [w for w in words if w not in stop_words and len(w) > 3 and w.isalpha()]
