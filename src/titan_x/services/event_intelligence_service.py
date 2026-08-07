from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.event_intelligence import EventDetection, EventImpactHistory
from titan_x.models.news_nlp import NewsNLPAnalysis, NewsEntity
from titan_x.models.news import NewsArticle
from titan_x.db.repository import BaseRepository

logger = structlog.get_logger(__name__)

POSITIVE_EVENTS = [
    "earnings_beat", "revenue_beat", "guidance_upgrade",
    "dividend_increase", "buyback", "contract_win",
    "partnership", "expansion", "regulatory_approval",
    "rating_upgrade", "insider_buying",
]
NEGATIVE_EVENTS = [
    "earnings_miss", "revenue_miss", "guidance_downgrade",
    "dividend_cut", "lawsuit", "investigation",
    "regulatory_action", "rating_downgrade", "insider_selling",
    "default", "restructuring", "layoff",
]
NEUTRAL_EVENTS = [
    "management_change", "merger_announcement", "acquisition",
    "spinoff", "stock_split", "rights_issue",
]


class EventIntelligenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.event_repo = BaseRepository(session, EventDetection)
        self.impact_repo = BaseRepository(session, EventImpactHistory)

    async def detect_from_news(self, article_id: int) -> list[EventDetection]:
        result = await self.session.execute(
            select(NewsArticle).where(NewsArticle.id == article_id)
        )
        article = result.scalar_one_or_none()
        if not article:
            return []

        result = await self.session.execute(
            select(NewsNLPAnalysis).where(NewsNLPAnalysis.article_id == article_id)
        )
        nlp = result.scalar_one_or_none()
        if not nlp:
            return []

        result = await self.session.execute(
            select(NewsEntity).where(NewsEntity.article_id == article_id)
        )
        entities = list(result.scalars().all())

        detected: list[EventDetection] = []
        events = self._parse_events(nlp.detected_events)

        for evt_name in events:
            evt_type = self._classify_event(evt_name)
            impact = self._compute_impact(evt_name, nlp)
            confidence = nlp.event_confidence or nlp.overall_confidence or 0.5

            detection = EventDetection(
                symbol=article.symbol or nlp.mapped_company_symbol or "unknown",
                event_type=evt_type,
                event_label=evt_name,
                impact_score=impact,
                confidence=confidence,
                source="news_nlp",
                description=f"Detected {evt_name} from news article: {article.title[:200]}",
                detected_at=datetime.now(timezone.utc),
                event_date=article.published_at.date() if article.published_at else date.today(),
                related_symbols=",".join(e.entity_text for e in entities[:10]) if entities else None,
                article_id=article_id,
            )
            self.session.add(detection)
            detected.append(detection)

        await self.session.flush()
        for d in detected:
            await self.session.refresh(d)
        return detected

    async def detect_all_recent(self, hours: int = 24) -> list[EventDetection]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.session.execute(
            select(NewsNLPAnalysis.article_id).where(
                NewsNLPAnalysis.processed_at >= cutoff,
                NewsNLPAnalysis.detected_events.isnot(None),
            )
        )
        article_ids = [r[0] for r in result.all()]
        all_detected: list[EventDetection] = []
        for aid in article_ids:
            try:
                detections = await self.detect_from_news(aid)
                all_detected.extend(detections)
            except Exception as e:
                logger.error("event_detect_error", article_id=aid, error=str(e))
        return all_detected

    async def get_events(
        self, symbol: str | None = None, event_type: str | None = None,
        start_date: date | None = None, end_date: date | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[EventDetection]:
        stmt = select(EventDetection)
        if symbol:
            stmt = stmt.where(EventDetection.symbol == symbol.upper())
        if event_type:
            stmt = stmt.where(EventDetection.event_type == event_type)
        if start_date:
            stmt = stmt.where(EventDetection.event_date >= start_date)
        if end_date:
            stmt = stmt.where(EventDetection.event_date <= end_date)
        stmt = stmt.order_by(desc(EventDetection.detected_at)).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_events(
        self, symbol: str | None = None, event_type: str | None = None,
        start_date: date | None = None, end_date: date | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(EventDetection)
        if symbol:
            stmt = stmt.where(EventDetection.symbol == symbol.upper())
        if event_type:
            stmt = stmt.where(EventDetection.event_type == event_type)
        if start_date:
            stmt = stmt.where(EventDetection.event_date >= start_date)
        if end_date:
            stmt = stmt.where(EventDetection.event_date <= end_date)
        return (await self.session.execute(stmt)).scalar() or 0

    async def get_event_summary(
        self, symbol: str, days: int = 30,
    ) -> dict[str, Any]:
        start = date.today() - timedelta(days=days)
        events = await self.get_events(symbol=symbol, start_date=start)
        total = len(events)
        positive = sum(1 for e in events if e.event_type == "positive")
        negative = sum(1 for e in events if e.event_type == "negative")
        neutral = sum(1 for e in events if e.event_type == "neutral")
        avg_impact = sum(e.impact_score for e in events) / total if total else 0
        net = avg_impact * (positive - negative) / max(total, 1)
        return {
            "symbol": symbol,
            "period_days": days,
            "total_events": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "avg_impact": round(avg_impact, 4),
            "net_impact": round(net, 4),
            "event_types": list(set(e.event_label for e in events)),
        }

    async def compute_daily_impact(self, target_date: date | None = None) -> EventImpactHistory:
        if target_date is None:
            target_date = date.today()
        start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        result = await self.session.execute(
            select(EventDetection).where(
                EventDetection.detected_at >= start,
                EventDetection.detected_at <= end,
            )
        )
        events = list(result.scalars().all())

        positive = [e for e in events if e.event_type == "positive"]
        negative = [e for e in events if e.event_type == "negative"]
        neutral = [e for e in events if e.event_type == "neutral"]

        top = sorted(
            [{"label": e.event_label, "symbol": e.symbol, "impact": e.impact_score}
             for e in events],
            key=lambda x: -abs(x["impact"]),
        )[:10]

        history = EventImpactHistory(
            symbol="MARKET",
            impact_date=target_date,
            event_type="all",
            total_positive=len(positive),
            total_negative=len(negative),
            total_neutral=len(neutral),
            avg_positive_impact=round(sum(e.impact_score for e in positive) / len(positive), 4) if positive else None,
            avg_negative_impact=round(sum(e.impact_score for e in negative) / len(negative), 4) if negative else None,
            net_impact_score=sum(e.impact_score for e in positive) - sum(e.impact_score for e in negative),
            top_events_json=str(top),
        )
        self.session.add(history)
        await self.session.flush()
        await self.session.refresh(history)
        return history

    def _parse_events(self, detected_events: str | None) -> list[str]:
        if not detected_events:
            return []
        import json
        try:
            parsed = json.loads(detected_events)
            if isinstance(parsed, list):
                return [str(e) for e in parsed]
            if isinstance(parsed, dict):
                return [str(k) for k in parsed.keys()]
            return [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            return [e.strip() for e in detected_events.split(",") if e.strip()]

    def _classify_event(self, event_name: str) -> str:
        lower = event_name.lower().replace(" ", "_")
        if lower in POSITIVE_EVENTS or any(p in lower for p in ["beat", "upgrade", "increase", "approval", "win", "buyback"]):
            return "positive"
        if lower in NEGATIVE_EVENTS or any(n in lower for n in ["miss", "cut", "lawsuit", "downgrade", "default", "layoff"]):
            return "negative"
        return "neutral"

    def _compute_impact(self, event_name: str, nlp: NewsNLPAnalysis) -> float:
        base = nlp.overall_confidence or 0.5
        sentiment = nlp.sentiment_label or "neutral"
        if sentiment == "positive":
            return round(base * 1.0, 4)
        if sentiment == "negative":
            return round(base * -1.0, 4)
        return round(base * 0.3, 4)
