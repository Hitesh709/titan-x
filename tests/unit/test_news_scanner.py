"""Tests for News Scanner service."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.news import NewsArticle, NewsArticleCategory, NewsCategory
from titan_x.models.news_nlp import NewsEntity, NewsNLPAnalysis
from titan_x.services.news_scanner_service import NewsScannerService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @event.listens_for(eng.sync_engine, "connect")
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
    SessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def service(session):
    return NewsScannerService(session)


@pytest_asyncio.fixture
async def company(session):
    c = Company(symbol="RELIANCE", company_name="Reliance Industries Ltd", isin="INE002A01018", exchange="NSE", status="active")
    session.add(c)
    await session.commit()
    return c


@pytest_asyncio.fixture
async def categories(session):
    cat_data = {
        "economy": "Macroeconomic news and indicators",
        "regulation": "Regulatory and compliance news",
        "markets": "Market commentary and analysis",
        "industry": "Industry-specific news and trends",
        "earnings": "Earnings reports and financial results",
        "technology": "Technology and innovation news",
    }
    cats = {}
    for name, desc in cat_data.items():
        c = NewsCategory(name=name, description=desc)
        session.add(c)
        cats[name] = c
    await session.commit()
    return cats


async def _make_article(
    session, title: str, symbol: str | None = None,
    categories_list: list[NewsCategory] | None = None,
    sentiment: str = "neutral", confidence: float = 0.5,
    sector: str | None = None, events: list[str] | None = None,
    entities: list[str] | None = None,
    published_at: datetime | None = None,
) -> NewsArticle:
    a = NewsArticle(
        title=title,
        summary=f"Summary of {title}",
        source="test_source",
        source_id=title.lower().replace(" ", "_"),
        url=f"https://example.com/{title.lower().replace(' ', '_')}",
        url_hash=title.lower().replace(" ", "_"),
        symbol=symbol,
        published_at=published_at or datetime.now(timezone.utc),
    )
    session.add(a)
    await session.flush()

    if categories_list:
        for cat in categories_list:
            link = NewsArticleCategory(article_id=a.id, category_id=cat.id)
            session.add(link)

    nlp = NewsNLPAnalysis(
        article_id=a.id,
        is_processed=True,
        processed_at=datetime.now(timezone.utc),
        sentiment_label=sentiment,
        sentiment_positive=0.6 if sentiment == "positive" else 0.2,
        sentiment_negative=0.6 if sentiment == "negative" else 0.2,
        sentiment_neutral=0.6 if sentiment == "neutral" else 0.2,
        sentiment_confidence=confidence,
        detected_events=json.dumps([{"event_type": e, "category": "general"} for e in (events or [])]) if events else None,
        event_confidence=confidence,
        mapped_sector=sector,
        sector_confidence=confidence,
        mapped_company_symbol=symbol,
        company_confidence=confidence if symbol else None,
        overall_confidence=confidence,
    )
    session.add(nlp)
    await session.flush()

    for ent in (entities or []):
        e = NewsEntity(
            article_id=a.id,
            entity_text=ent,
            entity_type="ORGANIZATION",
            confidence=0.8,
        )
        session.add(e)

    return a


class TestScannerCore:
    async def test_scan_no_articles(self, service: NewsScannerService):
        result = await service.scan(days=7)
        assert result["total_articles"] == 0
        for cat in ["company", "sector", "macro", "government", "global"]:
            assert result["categories"][cat]["article_count"] == 0

    async def test_scan_company_category(self, service: NewsScannerService, session):
        now = datetime.now(timezone.utc)
        await _make_article(session, "RELIANCE Q3 Results Beat Estimates", symbol="RELIANCE",
                      sentiment="positive", confidence=0.85, sector="energy", events=["earnings_beat"],
                      entities=["RELIANCE", "Reliance Industries"], published_at=now)
        await _make_article(session, "TCS Wins Mega Deal", symbol="TCS",
                      sentiment="positive", confidence=0.75, sector="technology", events=["partnership"],
                      entities=["TCS"], published_at=now - timedelta(hours=6))
        await _make_article(session, "General Economy News", symbol=None,
                      sentiment="neutral", confidence=0.5, published_at=now)
        await session.commit()

        result = await service.scan(days=7)
        assert result["total_articles"] == 3
        company = result["categories"]["company"]
        assert company["article_count"] == 2
        assert company["dominant_sentiment"] == "positive"
        assert len(company["tags"]) > 0
        assert any(t["tag"] == "bullish_sentiment" for t in company["tags"])
        assert any("symbol:RELIANCE" in t["tag"] for t in company["tags"])

    async def test_scan_sector_category(self, service: NewsScannerService, session):
        now = datetime.now(timezone.utc)
        await _make_article(session, "Tech Rally Continues", symbol="AAPL",
                      sentiment="positive", confidence=0.8, sector="technology",
                      entities=["AAPL", "Apple"], published_at=now)
        await _make_article(session, "Oil Prices Surge", symbol="XOM",
                      sentiment="positive", confidence=0.7, sector="energy",
                      entities=["XOM"], published_at=now)
        await _make_article(session, "Banking Sector Concerns", symbol="JPM",
                      sentiment="negative", confidence=0.9, sector="financial_services",
                      entities=["JPM"], published_at=now)
        await session.commit()

        result = await service.scan(days=7)
        sector = result["categories"]["sector"]
        assert sector["article_count"] == 3
        assert len(sector["top_sectors"]) >= 3

    async def test_scan_macro_category(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        await _make_article(session, "Fed Holds Interest Rates Steady",
                      categories_list=[categories["economy"]],
                      sentiment="neutral", confidence=0.8, published_at=now)
        await _make_article(session, "GDP Growth Exceeds Expectations",
                      categories_list=[categories["economy"]],
                      sentiment="positive", confidence=0.9, published_at=now)
        await session.commit()

        result = await service.scan(days=7)
        macro = result["categories"]["macro"]
        assert macro["article_count"] == 2
        assert macro["dominant_sentiment"] == "positive"

    async def test_scan_government_category(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        await _make_article(session, "SEC Launches Investigation",
                      categories_list=[categories["regulation"]],
                      sentiment="negative", confidence=0.85,
                      events=["investigation"], published_at=now)
        await _make_article(session, "New Compliance Rules Announced",
                      categories_list=[categories["regulation"]],
                      sentiment="neutral", confidence=0.7, published_at=now)
        await session.commit()

        result = await service.scan(days=7)
        govt = result["categories"]["government"]
        assert govt["article_count"] == 2

    async def test_scan_global_category(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        await _make_article(session, "Global Markets Rally on Trade Deal",
                      categories_list=[categories["markets"]],
                      sentiment="positive", confidence=0.8, published_at=now)
        await _make_article(session, "Supply Chain Disruptions Impact Industries",
                      categories_list=[categories["industry"]],
                      sentiment="negative", confidence=0.75, published_at=now)
        await session.commit()

        result = await service.scan(days=7)
        global_cat = result["categories"]["global"]
        assert global_cat["article_count"] == 2

    async def test_scan_category_counts(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        await _make_article(session, "RELIANCE Earnings", symbol="RELIANCE",
                      sentiment="positive", confidence=0.8, sector="energy",
                      categories_list=[categories["economy"]],
                      events=["earnings_beat"], entities=["RELIANCE"], published_at=now)
        await _make_article(session, "SEC Fines Bank", symbol="JPM",
                      sentiment="negative", confidence=0.9, sector="financial_services",
                      categories_list=[categories["regulation"]],
                      events=["fine_penalty"], entities=["JPM"], published_at=now)
        await _make_article(session, "Tech Sector Growth", symbol="MSFT",
                      sentiment="positive", confidence=0.7, sector="technology",
                      categories_list=[categories["markets"]],
                      entities=["MSFT"], published_at=now)
        await session.commit()

        result = await service.scan(days=7)
        counts = result["category_counts"]
        assert counts["company"] >= 3
        assert counts["sector"] >= 3
        assert counts["macro"] >= 1
        assert counts["government"] >= 1
        assert counts["global"] >= 1

    async def test_scan_category_only(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        await _make_article(session, "RELIANCE Q3 Results", symbol="RELIANCE",
                      sentiment="positive", confidence=0.85, sector="energy",
                      events=["earnings_beat"], published_at=now)
        await _make_article(session, "Fed Decision", categories_list=[categories["economy"]],
                      sentiment="neutral", confidence=0.8, published_at=now)
        await session.commit()

        result = await service.scan_category("macro", days=7)
        assert result["article_count"] == 1
        assert result["dominant_sentiment"] == "neutral"

    async def test_scan_respects_lookback(self, service: NewsScannerService, session):
        old = datetime.now(timezone.utc) - timedelta(days=30)
        recent = datetime.now(timezone.utc)
        await _make_article(session, "Old News", symbol="OLD", sentiment="neutral", confidence=0.5, published_at=old)
        await _make_article(session, "Recent News", symbol="NEW", sentiment="positive", confidence=0.8, published_at=recent)
        await session.commit()

        result = await service.scan(days=7)
        assert result["total_articles"] == 1
        assert result["categories"]["company"]["article_count"] == 1

    async def test_tags_generated(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        await _make_article(session, "RELIANCE Beat Estimates Raises Guidance", symbol="RELIANCE",
                      sentiment="positive", confidence=0.9, sector="energy",
                      categories_list=[categories["economy"], categories["markets"]],
                      events=["earnings_beat", "guidance_raised"],
                      entities=["RELIANCE", "Reliance Industries", "Mukesh Ambani"],
                      published_at=now)
        await session.commit()

        result = await service.scan(days=7)
        company = result["categories"]["company"]
        tags = company["tags"]
        tag_labels = [t["tag"] for t in tags]
        assert "bullish_sentiment" in tag_labels
        assert any("event:" in t for t in tag_labels)
        assert any("sector:" in t for t in tag_labels)
        assert any("symbol:" in t for t in tag_labels)
        assert "high_confidence" in tag_labels

    async def test_empty_scan_category(self, service: NewsScannerService):
        result = await service.scan_category("company", days=7)
        assert result["article_count"] == 0


class TestArticleDict:
    async def test_article_dict_maps_correctly(self, service: NewsScannerService, session):
        now = datetime.now(timezone.utc)
        a = await _make_article(session, "Test Article", symbol="TEST",
                          sentiment="positive", confidence=0.8, sector="technology",
                          events=["earnings_beat"], entities=["TEST Corp"],
                          published_at=now)
        await session.commit()
        await session.refresh(a, ["nlp_analysis", "entities", "categories"])

        d = service._article_dict(a)
        assert d["title"] == "Test Article"
        assert d["symbol"] == "TEST"
        assert d["sentiment_label"] == "positive"
        assert d["overall_confidence"] == 0.8
        assert d["mapped_sector"] == "technology"
        assert "TEST Corp" in d["entities"]
        assert "earnings_beat" in d["events"]

    async def test_article_dict_no_nlp(self, service: NewsScannerService, session):
        a = NewsArticle(
            title="No NLP", source="test", source_id="no_nlp",
            url="https://example.com/no_nlp", url_hash="no_nlp",
        )
        session.add(a)
        await session.commit()
        await session.refresh(a, ["nlp_analysis", "entities", "categories"])

        d = service._article_dict(a)
        assert d["sentiment_label"] is None
        assert d["overall_confidence"] is None
        assert d["entities"] == []
        assert d["events"] == []


class TestExtractKeywords:
    def test_extract_keywords(self, service: NewsScannerService):
        title = "RELIANCE Beat Estimates Raises Guidance for Next Quarter"
        keywords = service._extract_keywords(title)
        assert "reliance" in keywords
        assert "estimates" in keywords
        assert "raises" in keywords
        assert "guidance" in keywords
        assert "quarter" in keywords
        assert "the" not in keywords

    def test_extract_keywords_empty(self, service: NewsScannerService):
        assert service._extract_keywords("") == []

    def test_extract_keywords_short_words(self, service: NewsScannerService):
        assert service._extract_keywords("a an is to be") == []


class TestCategorize:
    async def test_categorize_company(self, service: NewsScannerService, session):
        now = datetime.now(timezone.utc)
        a = await _make_article(session, "Company News", symbol="ABC",
                          sentiment="neutral", confidence=0.5, published_at=now)
        await session.commit()
        await session.refresh(a, ["nlp_analysis", "entities", "categories"])
        d = service._article_dict(a)

        by_cat = service._categorize([d])
        assert len(by_cat["company"]) == 1

    async def test_categorize_macro(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        a = await _make_article(session, "Economy News",
                          categories_list=[categories["economy"]],
                          sentiment="neutral", confidence=0.5, published_at=now)
        await session.commit()
        await session.refresh(a, ["nlp_analysis", "entities", "categories"])
        d = service._article_dict(a)

        by_cat = service._categorize([d])
        assert len(by_cat["macro"]) == 1

    async def test_categorize_government(self, service: NewsScannerService, session, categories):
        now = datetime.now(timezone.utc)
        a = await _make_article(session, "Regulation News",
                          categories_list=[categories["regulation"]],
                          sentiment="neutral", confidence=0.5, published_at=now)
        await session.commit()
        await session.refresh(a, ["nlp_analysis", "entities", "categories"])
        d = service._article_dict(a)

        by_cat = service._categorize([d])
        assert len(by_cat["government"]) == 1
