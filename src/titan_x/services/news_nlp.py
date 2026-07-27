import json
import math
import re
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsEntity, NewsNLPAnalysis

logger = structlog.get_logger(__name__)

FINANCIAL_POSITIVE_WORDS: set[str] = {
    "beat", "beats", "surge", "surges", "soar", "soars", "rally", "rallies",
    "growth", "grew", "profit", "profitable", "upgrade", "upgraded", "outperform",
    "bullish", "positive", "strong", "strength", "gain", "gains", "record",
    "exceed", "exceeded", "exceeds", "raised", "raise", "guidance raised",
    "buyback", "dividend increase", "expansion", "expand", "momentum",
    "recovery", "rebound", "optimistic", "confidence", "innovate", "innovation",
    "breakthrough", "approval", "approved", "launch", "partnership",
}

FINANCIAL_NEGATIVE_WORDS: set[str] = {
    "miss", "misses", "missed", "decline", "declines", "plunge", "plunges",
    "drop", "drops", "slump", "slumps", "fall", "falls", "fell", "downgrade",
    "downgraded", "underperform", "bearish", "negative", "weak", "weakness",
    "loss", "losses", "layoff", "layoffs", "fired", "investigation", "fine",
    "penalty", "lawsuit", " litigation", "fraud", "scandal", "restructuring",
    "bankruptcy", "default", "downturn", "slowdown", "recession", "inflation",
    "volatile", "volatility", "uncertainty", "risk", "debt", "deficit",
    "write-down", "impairment", "charge", "provision", "cut", "cuts",
}

FINANCIAL_NEUTRAL_WORDS: set[str] = {
    "announced", "announces", "announcement", "report", "reports", "reported",
    "release", "released", "publish", "published", "statement", "said",
    "according", "filed", "filing", "update", "updated", "appointed",
    "appointment", "resigned", "resignation", "elected", "board",
    "quarterly", "annual", "fiscal", "quarter", "Q1", "Q2", "Q3", "Q4",
    "guidance", "outlook", "forecast", "expected", "estimate", "estimates",
    "analyst", "analysts", "consensus", "target", "price target",
}

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "technology": ["technology", "software", "hardware", "semiconductor", "chip", "cloud", "saas", "ai", "artificial intelligence", "data center", "cybersecurity", "tech"],
    "financial_services": ["bank", "insurance", "fintech", "lending", "mortgage", "asset management", "wealth management", "brokerage", "exchange"],
    "healthcare": ["healthcare", "pharmaceutical", "biotech", "medical", "hospital", "drug", "therapeutics", "clinical trial", "fda", "diagnostics"],
    "energy": ["energy", "oil", "gas", "renewable", "solar", "wind", "petroleum", "refining", "utility", "nuclear"],
    "consumer_goods": ["retail", "consumer", "e-commerce", "fashion", "food", "beverage", "restaurant", "luxury", "apparel"],
    "industrial": ["industrial", "manufacturing", "aerospace", "defense", "machinery", "construction", "engineering", "transportation", "logistics"],
    "media": ["media", "entertainment", "streaming", "broadcast", "publishing", "gaming", "social media", "advertising", "news"],
    "telecommunications": ["telecom", "telecommunications", "5g", "wireless", "broadband", "network", "internet service"],
    "real_estate": ["real estate", "reit", "property", "commercial real estate", "residential", "rental"],
    "materials": ["materials", "mining", "metal", "steel", "chemical", "commodity", "agriculture", "paper", "packaging"],
}

EVENT_PATTERNS: list[tuple[str, str, list[str]]] = [
    ("earnings", "earnings_release", ["earnings", "quarterly result", "fiscal result", "reports earnings", "announces earnings", "Q1", "Q2", "Q3", "Q4", "fiscal year"]),
    ("earnings", "earnings_beat", ["beat estimates", "beat expectations", "surprise earnings", "above estimates", "exceed expectations"]),
    ("earnings", "earnings_miss", ["miss estimates", "miss expectations", "below estimates", "fell short", "disappoints"]),
    ("earnings", "guidance_raised", ["raises guidance", "raised guidance", "upgrades outlook", "positive guidance"]),
    ("earnings", "guidance_lowered", ["lowers guidance", "lowered guidance", "cuts guidance", "reduces outlook", "negative guidance"]),
    ("ma", "merger_announced", ["announces merger", "to merge", "agrees to merge", "merger agreement"]),
    ("ma", "acquisition_announced", ["announces acquisition", "to acquire", "agrees to acquire", "to buy", "to purchase"]),
    ("ma", "acquisition_completed", ["completes acquisition", "closes acquisition", "acquisition completed"]),
    ("ma", "takeover_bid", ["takeover bid", "takeover offer", "hostile takeover", "unsolicited bid"]),
    ("ma", "spin_off", ["spin-off", "spinoff", "spins off", "to separate", "divestiture", "divest"]),
    ("corporate_action", "dividend_declared", ["declares dividend", "announces dividend", "dividend of", "dividend payment"]),
    ("corporate_action", "buyback_announced", ["buyback", "share repurchase", "repurchase program", "buy back"]),
    ("corporate_action", "stock_split", ["stock split", "share split", "reverse split", "forward split"]),
    ("regulatory", "sec_filing", ["sec filing", "8-k", "10-k", "10-q", "filing with sec", "regulatory filing"]),
    ("regulatory", "investigation", ["investigation", "investigating", "probe", "inquiry", "regulatory review"]),
    ("regulatory", "fine_penalty", ["fined", "penalty", "sanction", "settlement", "regulatory fine"]),
    ("regulatory", "approval_granted", ["approval", "approved", "greenlight", "authorized", "clearance"]),
    ("leadership", "ceo_change", ["ceo", "chief executive", "appoints new", "resigns", "steps down", "named ceo", "leadership change"]),
    ("leadership", "board_change", ["board member", "board of directors", "appointed to board", "joins board"]),
    ("financing", "ipo", ["ipo", "initial public offering", "goes public", "listing", "stock exchange listing"]),
    ("financing", "capital_raise", ["capital raise", "funding round", "raises capital", "equity offering", "debt offering", "bonds"]),
    ("partnership", "partnership", ["partnership", "strategic alliance", "joint venture", "collaboration", "teams up"]),
    ("product", "product_launch", ["launches", "unveils", "introduces", "new product", "next-generation"]),
    ("product", "product_recall", ["recall", "safety concern", "defect", "quality issue"]),
]

UPPER_WORD_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


class SentimentAnalyzer:
    def analyze(self, title: str, content: str | None) -> dict[str, Any]:
        text = (title or "") + " " + (content or "")
        text_lower = text.lower()

        pos_count = sum(1 for w in FINANCIAL_POSITIVE_WORDS if w in text_lower)
        neg_count = sum(1 for w in FINANCIAL_NEGATIVE_WORDS if w in text_lower)
        neu_count = sum(1 for w in FINANCIAL_NEUTRAL_WORDS if w in text_lower)

        total = pos_count + neg_count + neu_count
        if total == 0:
            return {"label": "neutral", "positive": 0.0, "negative": 0.0, "neutral": 1.0, "confidence": 0.0}

        pos_score = pos_count / total
        neg_score = neg_count / total
        neu_score = neu_count / total

        if pos_score > neg_score and pos_score > neu_score:
            label = "positive"
        elif neg_score > pos_score and neg_score > neu_score:
            label = "negative"
        else:
            label = "neutral"

        signal_strength = max(pos_score, neg_score, neu_score) - (1 / 3)
        confidence = min(1.0, max(0.0, signal_strength * 2.0))

        return {"label": label, "positive": round(pos_score, 4), "negative": round(neg_score, 4), "neutral": round(neu_score, 4), "confidence": round(confidence, 4)}


class NERExtractor:
    TICKER_PATTERN = re.compile(r"\b[A-Z]{1,5}\b")
    COMPANY_NAME_PATTERN = re.compile(
        r"\b([A-Z][a-zA-Z]+(?:\s+(?:[A-Z][a-zA-Z]+|&|and|of|the|Inc|Corp|Ltd|LLC|PLC|Group|Holdings|Technologies|Solutions|Systems|Industries|Partners|Capital|Ventures|Energy|Power|Mining|Pharma|Bio|Tech|Health|Care|Financial|Insurance|Bank|Trust|Asset|Management)){0,5})\b"
    )

    def extract(self, title: str, content: str | None) -> list[dict[str, Any]]:
        text = (title or "") + " " + (content or "")
        entities: list[dict[str, Any]] = []
        seen: set[str] = set()

        tickers = self.TICKER_PATTERN.findall(text)
        common_words = {"THE", "AND", "FOR", "OUR", "NEW", "ALL", "ITS", "HAS", "ARE", "NOT", "WAS", "BUT", "YOU", "THAT", "CAN", "WILL", "JUST", "WITH", "THIS", "FROM", "YOUR", "BEEN", "HAVE"}
        for t in tickers:
            if t not in common_words and t not in seen:
                seen.add(t)
                entities.append({"entity_text": t, "entity_type": "TICKER", "confidence": 0.5})

        company_matches = self.COMPANY_NAME_PATTERN.findall(text)
        for cm in company_matches:
            cm = cm.strip()
            if len(cm) >= 4 and cm not in seen:
                seen.add(cm)
                entities.append({"entity_text": cm, "entity_type": "ORGANIZATION", "confidence": 0.4})

        return entities


class CompanyMapper:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    async def map(self, session: AsyncSession, entities: list[dict[str, Any]], article_symbol: str | None) -> tuple[str | None, float]:
        candidates: list[str] = []

        for ent in entities:
            if ent["entity_type"] == "TICKER":
                result = await session.execute(
                    select(Company.symbol).where(Company.symbol == ent["entity_text"])
                )
                if result.scalar_one_or_none() is not None:
                    candidates.append(ent["entity_text"])

        if article_symbol:
            result = await session.execute(
                select(Company.symbol).where(Company.symbol == article_symbol.upper())
            )
            if result.scalar_one_or_none() is not None:
                candidates.append(article_symbol.upper())

        for ent in entities:
            if ent["entity_type"] == "ORGANIZATION":
                name_lower = ent["entity_text"].lower()
                result = await session.execute(
                    select(Company.symbol, Company.company_name)
                )
                rows = result.all()
                for symbol, company_name in rows:
                    if company_name and name_lower in company_name.lower():
                        candidates.append(symbol)
                        break

        if not candidates:
            return None, 0.0

        best = max(set(candidates), key=candidates.count)
        confidence = min(1.0, 0.3 + (candidates.count(best) / max(len(candidates), 1)) * 0.7)
        return best, round(confidence, 4)


class SectorMapper:
    def map(self, title: str, content: str | None) -> tuple[str | None, float]:
        text = (title or "") + " " + (content or "")
        text_lower = text.lower()

        matches: dict[str, int] = {}
        for sector, keywords in SECTOR_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > 0:
                matches[sector] = count

        if not matches:
            return None, 0.0

        best = max(matches, key=matches.get)
        total_matches = sum(matches.values())
        confidence = min(1.0, round(matches[best] / total_matches, 4))
        return best, confidence


class EventDetector:
    def detect(self, title: str, content: str | None) -> tuple[list[dict[str, str]], float]:
        text = (title or "") + " " + (content or "")
        text_lower = text.lower()

        detected: list[dict[str, str]] = []
        match_count = 0
        total_patterns = 0

        for category, event_type, keywords in EVENT_PATTERNS:
            for kw in keywords:
                total_patterns += 1
                if kw in text_lower:
                    detected.append({"category": category, "event_type": event_type, "keyword": kw})
                    match_count += 1
                    break

        if match_count == 0:
            return [], 0.0

        confidence = min(1.0, round(match_count / max(total_patterns, 1) * 10, 4))
        return detected, confidence


class ConfidenceScorer:
    def score(
        self,
        sentiment_conf: float,
        event_conf: float,
        sector_conf: float,
        company_conf: float,
        entity_count: int,
        has_article_symbol: bool,
    ) -> float:
        components = [
            sentiment_conf * 0.20,
            min(event_conf * 2.0, 1.0) * 0.20,
            sector_conf * 0.15,
            company_conf * 0.15,
            min(entity_count / 10, 1.0) * 0.15,
            (0.15 if has_article_symbol else 0.0),
        ]
        return round(min(1.0, sum(components)), 4)


class NewsNLPEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._analysis_repo = BaseRepository(session, NewsNLPAnalysis)
        self._entity_repo = BaseRepository(session, NewsEntity)
        self._sentiment = SentimentAnalyzer()
        self._ner = NERExtractor()
        self._company_mapper = CompanyMapper()
        self._sector_mapper = SectorMapper()
        self._event_detector = EventDetector()
        self._confidence = ConfidenceScorer()

    async def process_article(self, article_id: int) -> NewsNLPAnalysis:
        result = await self._session.execute(
            select(NewsArticle)
            .where(NewsArticle.id == article_id)
            .options(selectinload(NewsArticle.nlp_analysis))
        )
        article = result.scalar_one_or_none()
        if article is None:
            raise ValueError(f"Article {article_id} not found")

        existing = await self._session.execute(
            select(NewsNLPAnalysis).where(NewsNLPAnalysis.article_id == article_id)
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("nlp_already_processed", article_id=article_id)
            return existing.scalar_one_or_none()

        sentiment = self._sentiment.analyze(article.title, (article.summary or "") + " " + (article.content or ""))
        entities = self._ner.extract(article.title, (article.summary or "") + " " + (article.content or ""))
        company_symbol, company_conf = await self._company_mapper.map(self._session, entities, article.symbol)
        sector, sector_conf = self._sector_mapper.map(article.title, article.content or article.summary)
        events, event_conf = self._event_detector.detect(article.title, article.content or article.summary)
        overall = self._confidence.score(
            sentiment["confidence"], event_conf, sector_conf, company_conf,
            len(entities), article.symbol is not None,
        )

        analysis = await self._analysis_repo.create(
            article_id=article_id, is_processed=True, processed_at=datetime.now(timezone.utc),
            sentiment_label=sentiment["label"],
            sentiment_positive=sentiment["positive"],
            sentiment_negative=sentiment["negative"],
            sentiment_neutral=sentiment["neutral"],
            sentiment_confidence=sentiment["confidence"],
            detected_events=json.dumps(events) if events else None,
            event_confidence=event_conf,
            mapped_sector=sector,
            sector_confidence=sector_conf,
            mapped_company_symbol=company_symbol,
            company_confidence=company_conf,
            overall_confidence=overall,
        )

        for ent in entities:
            await self._entity_repo.create(
                article_id=article_id, entity_text=ent["entity_text"],
                entity_type=ent["entity_type"], confidence=ent["confidence"],
            )

        await self._session.flush()
        logger.info("nlp_processing_complete", article_id=article_id, sentiment=sentiment["label"], sector=sector)
        return analysis

    async def get_analysis(self, article_id: int) -> NewsNLPAnalysis | None:
        result = await self._session.execute(
            select(NewsNLPAnalysis).where(NewsNLPAnalysis.article_id == article_id)
        )
        return result.scalar_one_or_none()

    async def get_entities(self, article_id: int) -> list[NewsEntity]:
        result = await self._session.execute(
            select(NewsEntity).where(NewsEntity.article_id == article_id).order_by(NewsEntity.confidence.desc().nullslast())
        )
        return list(result.scalars().all())

    async def process_unprocessed(self, limit: int = 50) -> int:
        result = await self._session.execute(
            select(NewsArticle.id)
            .outerjoin(NewsNLPAnalysis, NewsArticle.id == NewsNLPAnalysis.article_id)
            .where(NewsNLPAnalysis.id.is_(None))
            .limit(limit)
        )
        ids = [row[0] for row in result.all()]
        for aid in ids:
            try:
                await self.process_article(aid)
            except Exception as exc:
                logger.error("nlp_batch_error", article_id=aid, error=str(exc))
        return len(ids)

    async def search_by_sentiment(
        self, label: str, *, skip: int = 0, limit: int = 50,
    ) -> tuple[list[NewsArticle], int]:
        stmt = (
            select(NewsArticle)
            .join(NewsNLPAnalysis)
            .where(NewsNLPAnalysis.sentiment_label == label)
            .order_by(NewsNLPAnalysis.sentiment_confidence.desc().nullslast())
        )
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt.options(selectinload(NewsArticle.categories)))
        return list(result.scalars().all()), total

    async def search_by_sector(
        self, sector: str, *, skip: int = 0, limit: int = 50,
    ) -> tuple[list[NewsArticle], int]:
        stmt = (
            select(NewsArticle)
            .join(NewsNLPAnalysis)
            .where(NewsNLPAnalysis.mapped_sector == sector)
            .order_by(NewsArticle.published_at.desc().nullslast())
        )
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt.options(selectinload(NewsArticle.categories)))
        return list(result.scalars().all()), total

    async def search_by_event(
        self, event_type: str, *, skip: int = 0, limit: int = 50,
    ) -> tuple[list[NewsArticle], int]:
        pattern = f"%{event_type}%"
        stmt = (
            select(NewsArticle)
            .join(NewsNLPAnalysis)
            .where(NewsNLPAnalysis.detected_events.ilike(pattern))
            .order_by(NewsNLPAnalysis.event_confidence.desc().nullslast())
        )
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt.options(selectinload(NewsArticle.categories)))
        return list(result.scalars().all()), total

    async def get_nlp_stats(self) -> dict[str, Any]:
        from sqlalchemy import func

        total_result = await self._session.execute(select(func.count(NewsNLPAnalysis.id)))
        total_processed = total_result.scalar() or 0

        sentiment_result = await self._session.execute(
            select(NewsNLPAnalysis.sentiment_label, func.count(NewsNLPAnalysis.id))
            .group_by(NewsNLPAnalysis.sentiment_label)
        )
        per_sentiment = dict(sentiment_result.all())

        sector_result = await self._session.execute(
            select(NewsNLPAnalysis.mapped_sector, func.count(NewsNLPAnalysis.id))
            .where(NewsNLPAnalysis.mapped_sector.isnot(None))
            .group_by(NewsNLPAnalysis.mapped_sector)
        )
        per_sector = dict(sector_result.all())

        return {
            "total_processed": total_processed,
            "per_sentiment": per_sentiment,
            "per_sector": per_sector,
        }
