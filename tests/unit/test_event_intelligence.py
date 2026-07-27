import json
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.event_intelligence import EventDetection, EventImpactHistory
from titan_x.models.news import NewsArticle, NewsCategory
from titan_x.models.news_nlp import NewsEntity, NewsNLPAnalysis
from titan_x.services.event_intelligence_service import EventIntelligenceService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def service(session):
    return EventIntelligenceService(session)


@pytest_asyncio.fixture
async def article_with_nlp(session):
    cat = NewsCategory(name="earnings", description="Earnings")
    session.add(cat)
    article = NewsArticle(
        title="Test Corp beats estimates", source="test", source_id="t1",
        url="https://example.com/t1", url_hash="t1", symbol="TEST",
        published_at=datetime.now(timezone.utc),
    )
    session.add(article)
    await session.flush()

    nlp = NewsNLPAnalysis(
        article_id=article.id, is_processed=True,
        processed_at=datetime.now(timezone.utc),
        sentiment_label="positive", sentiment_positive=0.9,
        sentiment_confidence=0.85, overall_confidence=0.85,
        detected_events=json.dumps(["earnings_beat", "revenue_beat"]),
        event_confidence=0.8, mapped_company_symbol="TEST",
    )
    session.add(nlp)
    await session.flush()
    return article, nlp


class TestDetectEvents:
    async def test_detect_from_news(self, service, session, article_with_nlp):
        article, _ = article_with_nlp
        events = await service.detect_from_news(article.id)
        assert len(events) >= 2
        for e in events:
            assert e.event_type in ("positive", "negative", "neutral")
            assert e.impact_score != 0
            assert e.source == "news_nlp"
            assert e.article_id == article.id

    async def test_detect_from_news_no_nlp(self, service, session):
        article = NewsArticle(
            title="No NLP", source="test", source_id="t2",
            url="https://example.com/t2", url_hash="t2",
        )
        session.add(article)
        await session.flush()
        events = await service.detect_from_news(article.id)
        assert len(events) == 0

    async def test_detect_recent(self, service, session, article_with_nlp):
        events = await service.detect_all_recent(hours=48)
        assert len(events) >= 2

    async def test_classify_positive(self, service):
        assert service._classify_event("earnings_beat") == "positive"
        assert service._classify_event("revenue_beat") == "positive"
        assert service._classify_event("rating_upgrade") == "positive"

    async def test_classify_negative(self, service):
        assert service._classify_event("earnings_miss") == "negative"
        assert service._classify_event("lawsuit") == "negative"
        assert service._classify_event("layoff") == "negative"

    async def test_classify_neutral(self, service):
        assert service._classify_event("management_change") == "neutral"
        assert service._classify_event("stock_split") == "neutral"


class TestQueryEvents:
    async def test_get_events(self, service, session, article_with_nlp):
        article, _ = article_with_nlp
        await service.detect_from_news(article.id)
        events = await service.get_events()
        assert len(events) > 0

    async def test_get_events_by_symbol(self, service, session, article_with_nlp):
        article, _ = article_with_nlp
        await service.detect_from_news(article.id)
        events = await service.get_events(symbol="TEST")
        assert all(e.symbol == "TEST" for e in events)

    async def test_get_events_by_type(self, service, session, article_with_nlp):
        article, _ = article_with_nlp
        await service.detect_from_news(article.id)
        events = await service.get_events(event_type="positive")
        assert all(e.event_type == "positive" for e in events)

    async def test_event_summary_empty(self, service):
        summary = await service.get_event_summary("NONEXIST")
        assert summary["total_events"] == 0

    async def test_event_summary_with_data(self, service, session, article_with_nlp):
        article, _ = article_with_nlp
        await service.detect_from_news(article.id)
        summary = await service.get_event_summary("TEST", days=30)
        assert summary["total_events"] > 0
        assert summary["symbol"] == "TEST"


class TestImpactHistory:
    async def test_compute_daily_impact(self, service, session, article_with_nlp):
        article, _ = article_with_nlp
        await service.detect_from_news(article.id)
        history = await service.compute_daily_impact(date.today())
        assert history.impact_date == date.today()
        assert history.total_positive >= 2

    async def test_compute_daily_impact_empty(self, service):
        history = await service.compute_daily_impact(date.today())
        assert history.total_positive == 0
        assert history.total_negative == 0


class TestHelpers:
    def test_parse_events_list(self, service):
        result = service._parse_events('["earnings_beat", "revenue_beat"]')
        assert len(result) == 2
        assert "earnings_beat" in result

    def test_parse_events_dict(self, service):
        result = service._parse_events('{"earnings_beat": 0.9}')
        assert len(result) == 1

    def test_parse_events_csv(self, service):
        result = service._parse_events("earnings_beat, revenue_beat")
        assert len(result) == 2

    def test_parse_events_none(self, service):
        assert service._parse_events(None) == []

    def test_parse_events_empty(self, service):
        assert service._parse_events("") == []
