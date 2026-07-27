import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import desc, select

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.news import NewsArticle, NewsCategory
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.models.risk import RiskMetrics
from titan_x.models.saved_screen import SavedScreen
from titan_x.models.technical import TechnicalIndicator
from titan_x.models.user import User
from titan_x.services.advanced_screener_service import AdvancedScreenerService

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
async def users(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        u1 = User(email="user1@test.com", hashed_password="pw")
        u2 = User(email="user2@test.com", hashed_password="pw")
        s.add(u1); s.add(u2)
        await s.commit()
        yield {"user1": u1, "user2": u2}
        await s.close()


@pytest_asyncio.fixture
async def session(engine, users):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def seeded_session(session, users):
    today = date.today()


@pytest_asyncio.fixture
async def seeded_session(session):
    today = date.today()
    month_ago = today - timedelta(days=30)

    companies = {
        "AAPL": ("Apple Inc", "Technology", "Hardware", "NASDAQ", 2_500_000_000_000),
        "MSFT": ("Microsoft Corp", "Technology", "Software", "NASDAQ", 3_000_000_000_000),
        "JPM": ("JPMorgan Chase", "Financials", "Banking", "NYSE", 500_000_000_000),
        "BAC": ("Bank of America", "Financials", "Banking", "NYSE", 250_000_000_000),
        "XOM": ("Exxon Mobil", "Energy", "Oil", "NYSE", 400_000_000_000),
        "CVX": ("Chevron Corp", "Energy", "Oil", "NYSE", 300_000_000_000),
        "PG": ("Procter & Gamble", "Consumer", "Staples", "NYSE", 350_000_000_000),
    }

    for sym, (name, sector, industry, exchange, mcap) in companies.items():
        session.add(Company(symbol=sym, company_name=name, sector=sector, industry=industry, exchange=exchange, market_cap=mcap, isin=f"US{sym}01", status="active"))

    for sym, close, prev_close in [
        ("AAPL", 200.0, 180.0),
        ("MSFT", 350.0, 330.0),
        ("JPM", 180.0, 175.0),
        ("BAC", 40.0, 42.0),
        ("XOM", 120.0, 130.0),
        ("CVX", 145.0, 155.0),
        ("PG", 160.0, 155.0),
    ]:
        session.add(DailyPrice(symbol=sym, trade_date=month_ago, open=prev_close, high=prev_close, low=prev_close, close=prev_close, volume=1_000_000))
        session.add(DailyPrice(symbol=sym, trade_date=today, open=close, high=close, low=close, close=close, volume=2_000_000))

    session.add(TechnicalIndicator(symbol="AAPL", trade_date=today, indicator="rsi", params_hash="h1", value=65.0))
    session.add(TechnicalIndicator(symbol="MSFT", trade_date=today, indicator="rsi", params_hash="h1", value=55.0))
    session.add(TechnicalIndicator(symbol="JPM", trade_date=today, indicator="rsi", params_hash="h1", value=45.0))
    session.add(TechnicalIndicator(symbol="XOM", trade_date=today, indicator="rsi", params_hash="h1", value=30.0))

    session.add(TechnicalIndicator(symbol="AAPL", trade_date=today, indicator="macd", params_hash="h2", value=10.0, value_secondary=8.0))
    session.add(TechnicalIndicator(symbol="MSFT", trade_date=today, indicator="macd", params_hash="h2", value=5.0, value_secondary=6.0))
    session.add(TechnicalIndicator(symbol="JPM", trade_date=today, indicator="macd", params_hash="h2", value=2.0, value_secondary=3.0))

    for sym, pe, roe in [
        ("AAPL", 28.0, 0.35),
        ("MSFT", 32.0, 0.30),
        ("JPM", 12.0, 0.15),
        ("BAC", 10.0, 0.10),
        ("XOM", 15.0, 0.12),
        ("CVX", 18.0, 0.08),
        ("PG", 24.0, 0.20),
    ]:
        session.add(FundamentalMetric(symbol=sym, fiscal_year=2024, fiscal_period=4, period_type="annual", metric_name="PE_RATIO", value=float(pe)))
        session.add(FundamentalMetric(symbol=sym, fiscal_year=2024, fiscal_period=4, period_type="annual", metric_name="ROE", value=float(roe)))

    cat = NewsCategory(name="earnings")
    session.add(cat)
    await session.flush()

    for sym, pos, neg, conf in [
        ("AAPL", 0.7, 0.1, 0.8),
        ("MSFT", 0.6, 0.2, 0.7),
        ("JPM", 0.5, 0.3, 0.6),
        ("XOM", 0.3, 0.5, 0.5),
    ]:
        article = NewsArticle(symbol=sym, title=f"{sym} news", published_at=today - timedelta(days=1), source="test", source_id=f"s{sym}", url=f"http://{sym}.com", url_hash=f"h{sym}")
        session.add(article)
        await session.flush()
        session.add(NewsNLPAnalysis(article_id=article.id, sentiment_positive=pos, sentiment_negative=neg, sentiment_confidence=conf))

    for sym, liq_score, avg_vol in [
        ("AAPL", 85.0, 50_000_000),
        ("MSFT", 80.0, 40_000_000),
        ("JPM", 70.0, 15_000_000),
        ("BAC", 65.0, 12_000_000),
        ("XOM", 60.0, 10_000_000),
        ("CVX", 55.0, 8_000_000),
        ("PG", 75.0, 20_000_000),
    ]:
        session.add(RiskMetrics(symbol=sym, as_of_date=today, liquidity_score=liq_score, composite_risk_score=30.0, volatility_252d=25.0, avg_daily_volume_20d=avg_vol, avg_dollar_volume_20d=avg_vol * 100))

    for sym, ai_score, ai_signal, ai_conf in [
        ("AAPL", 75.0, "bullish", 80.0),
        ("MSFT", 68.0, "bullish", 70.0),
        ("JPM", 55.0, "neutral", 60.0),
        ("BAC", 45.0, "neutral", 55.0),
        ("XOM", 35.0, "bearish", 65.0),
        ("CVX", 30.0, "bearish", 60.0),
        ("PG", 60.0, "bullish", 65.0),
    ]:
        session.add(DynamicAIScore(symbol=sym, as_of_date=today, combined_score=ai_score, combined_signal=ai_signal, combined_confidence=ai_conf, technical_score=50.0, fundamental_score=50.0, news_score=50.0, macro_score=50.0, liquidity_score=50.0, risk_score=50.0, market_regime_score=50.0))

    await session.commit()
    return session


# ── Helper Tests ──

class TestHelpers:
    def test_service_imports(self):
        svc = AdvancedScreenerService.__new__(AdvancedScreenerService)
        assert svc is not None

    @pytest.mark.asyncio
    async def test_get_all_active_symbols(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        syms = await svc._get_all_active_symbols()
        assert len(syms) == 7
        assert "AAPL" in syms
        assert "XOM" in syms


# ── Company Filter Tests ──

@pytest.mark.asyncio
class TestCompanyFilter:
    async def test_filter_by_sector(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_companies({"sector": "Technology"})
        assert result == {"AAPL", "MSFT"}

    async def test_filter_by_multiple_sectors(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_companies({"sector": ["Technology", "Financials"]})
        assert result == {"AAPL", "MSFT", "JPM", "BAC"}

    async def test_filter_by_exchange(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_companies({"exchange": "NASDAQ"})
        assert result == {"AAPL", "MSFT"}

    async def test_filter_by_market_cap(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_companies({"market_cap": {"min": 1_000_000_000_000}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "JPM" not in result

    async def test_filter_by_industry(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_companies({"industry": "Banking"})
        assert result == {"JPM", "BAC"}


# ── Technical Filter Tests ──

@pytest.mark.asyncio
class TestTechnicalFilter:
    async def test_filter_rsi_range(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_technical({"rsi": {"min": 50, "max": 70}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "JPM" not in result
        assert "XOM" not in result

    async def test_filter_macd_bullish(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_technical({"macd": "bullish"})
        assert "AAPL" in result
        assert "MSFT" not in result
        assert "JPM" not in result

    async def test_filter_macd_bearish(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_technical({"macd": "bearish"})
        assert "MSFT" in result
        assert "JPM" in result
        assert "AAPL" not in result

    async def test_no_tech_data_returns_all(self, session):
        svc = AdvancedScreenerService(session)
        result = await svc._filter_technical({"rsi": {"min": 0}})
        assert result == set()


# ── Fundamental Filter Tests ──

@pytest.mark.asyncio
class TestFundamentalFilter:
    async def test_filter_pe_range(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_fundamental({"pe_ratio": {"min": 10, "max": 20}})
        assert "JPM" in result
        assert "XOM" in result
        assert "AAPL" not in result
        assert "MSFT" not in result

    async def test_filter_roe_min(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_fundamental({"roe": {"min": 0.25}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "JPM" not in result

    async def test_filter_pe_and_roe(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_fundamental({"pe_ratio": {"max": 20}, "roe": {"min": 0.10}})
        assert "JPM" in result
        assert "XOM" in result
        assert "CVX" not in result

    async def test_no_fund_data(self, session):
        svc = AdvancedScreenerService(session)
        result = await svc._filter_fundamental({"pe_ratio": {"min": 10}})
        assert result == set()


# ── News Filter Tests ──

@pytest.mark.asyncio
class TestNewsFilter:
    async def test_filter_positive_sentiment(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_news({"sentiment": {"min": 0.3}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "XOM" not in result

    async def test_filter_min_articles(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_news({"min_articles": 1, "sentiment": {"min": -1}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "JPM" in result

    async def test_no_news_data(self, session):
        svc = AdvancedScreenerService(session)
        result = await svc._filter_news({"sentiment": {"min": 0}})
        assert result == set()


# ── Liquidity Filter Tests ──

@pytest.mark.asyncio
class TestLiquidityFilter:
    async def test_filter_avg_volume(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_liquidity({"avg_volume_20d": {"min": 20_000_000}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "PG" in result
        assert "JPM" not in result

    async def test_filter_liquidity_score(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_liquidity({"liquidity_score": {"min": 75}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "PG" in result
        assert "BAC" not in result

    async def test_no_liq_data(self, session):
        svc = AdvancedScreenerService(session)
        result = await svc._filter_liquidity({"avg_volume_20d": {"min": 1000}})
        assert result == set()


# ── AI Score Filter Tests ──

@pytest.mark.asyncio
class TestAIScoreFilter:
    async def test_filter_combined_score(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_ai_score({"combined_score": {"min": 60}})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "PG" in result
        assert "JPM" not in result

    async def test_filter_by_signal(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_ai_score({"combined_signal": "bullish"})
        assert "AAPL" in result
        assert "MSFT" in result
        assert "PG" in result
        assert "JPM" not in result
        assert "XOM" not in result

    async def test_filter_by_min_confidence(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc._filter_ai_score({"min_confidence": 75, "combined_score": {"min": 0}})
        assert "AAPL" in result
        assert "MSFT" not in result

    async def test_no_ai_data(self, session):
        svc = AdvancedScreenerService(session)
        result = await svc._filter_ai_score({"combined_score": {"min": 50}})
        assert result == set()


# ── Combined Screen Tests ──

@pytest.mark.asyncio
class TestCombinedScreen:
    async def test_sector_and_pe(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({
            "sector": "Energy",
            "fundamental": {"pe_ratio": {"min": 10}},
        })
        assert result["total"] == 2
        symbols = {r["symbol"] for r in result["results"]}
        assert "XOM" in symbols
        assert "CVX" in symbols

    async def test_tech_and_rsi(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({
            "sector": "Technology",
            "technical": {"rsi": {"min": 50}},
        })
        assert result["total"] == 2
        symbols = {r["symbol"] for r in result["results"]}
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    async def test_ai_score_and_liquidity(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({
            "ai_score": {"combined_score": {"min": 60}, "combined_signal": "bullish"},
            "liquidity": {"avg_volume_20d": {"min": 10_000_000}},
        })
        assert 1 <= result["total"] <= 3

    async def test_news_sentiment_and_fundamentals(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({
            "news": {"sentiment": {"min": 0.3}},
            "fundamental": {"roe": {"min": 0.20}},
        })
        symbols = {r["symbol"] for r in result["results"]}
        assert "AAPL" in symbols or "MSFT" in symbols

    async def test_pagination(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({}, skip=0, limit=3)
        assert result["total"] == 7
        assert len(result["results"]) == 3

    async def test_all_filters_combined(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({
            "sector": "Technology",
            "technical": {"rsi": {"min": 50}},
            "fundamental": {"pe_ratio": {"min": 20}},
            "ai_score": {"combined_score": {"min": 60}},
        })
        assert result["total"] <= 2
        for r in result["results"]:
            assert r["sector"] == "Technology"

    async def test_no_matching_filters(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({
            "sector": "Technology",
            "fundamental": {"pe_ratio": {"max": 10}},
        })
        assert result["total"] == 0
        assert result["results"] == []

    async def test_results_include_company_info(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_screen({"sector": "Technology"})
        for r in result["results"]:
            assert "symbol" in r
            assert "company_name" in r
            assert "sector" in r
            assert "close" in r
            assert "change_1m_pct" in r


# ── Saved Screen Tests ──

@pytest.mark.asyncio
class TestSavedScreen:
    async def test_create_screen(self, session):
        svc = AdvancedScreenerService(session)
        screen = await svc.save_screen(
            user_id=1, name="Tech Value",
            filters_json='{"sector": "Technology", "fundamental": {"pe_ratio": {"max": 25}}}',
            description="Cheap tech stocks",
        )
        assert screen.id is not None
        assert screen.name == "Tech Value"
        assert screen.user_id == 1

    async def test_get_screen(self, session):
        svc = AdvancedScreenerService(session)
        screen = await svc.save_screen(user_id=1, name="Test", filters_json="{}")
        got = await svc.get_screen(screen.id, user_id=1)
        assert got is not None
        assert got.id == screen.id

    async def test_get_screen_wrong_user(self, session):
        svc = AdvancedScreenerService(session)
        screen = await svc.save_screen(user_id=1, name="Test", filters_json="{}")
        got = await svc.get_screen(screen.id, user_id=2)
        assert got is None

    async def test_list_screens(self, session):
        svc = AdvancedScreenerService(session)
        await svc.save_screen(user_id=1, name="S1", filters_json="{}")
        await svc.save_screen(user_id=1, name="S2", filters_json="{}")
        await svc.save_screen(user_id=2, name="S3", filters_json="{}")
        screens, total = await svc.list_screens(user_id=1)
        assert total == 2
        assert len(screens) == 2

    async def test_update_screen(self, session):
        svc = AdvancedScreenerService(session)
        screen = await svc.save_screen(user_id=1, name="Old", filters_json="{}")
        updated = await svc.update_screen(screen.id, user_id=1, name="New")
        assert updated is not None
        assert updated.name == "New"

    async def test_update_screen_wrong_user(self, session):
        svc = AdvancedScreenerService(session)
        screen = await svc.save_screen(user_id=1, name="Old", filters_json="{}")
        updated = await svc.update_screen(screen.id, user_id=2, name="New")
        assert updated is None

    async def test_delete_screen(self, session):
        svc = AdvancedScreenerService(session)
        screen = await svc.save_screen(user_id=1, name="Del", filters_json="{}")
        deleted = await svc.delete_screen(screen.id, user_id=1)
        assert deleted
        got = await svc.get_screen(screen.id, user_id=1)
        assert got is None

    async def test_delete_screen_wrong_user(self, session):
        svc = AdvancedScreenerService(session)
        screen = await svc.save_screen(user_id=1, name="Del", filters_json="{}")
        deleted = await svc.delete_screen(screen.id, user_id=2)
        assert not deleted

    async def test_run_saved_screen(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        screen = await svc.save_screen(
            user_id=1, name="Tech",
            filters_json=json.dumps({"sector": "Technology"}),
        )
        result = await svc.run_saved_screen(screen.id, user_id=1)
        assert result is not None
        assert result["total"] == 2
        assert screen.last_results_count == 2

    async def test_run_saved_screen_not_found(self, seeded_session):
        svc = AdvancedScreenerService(seeded_session)
        result = await svc.run_saved_screen(9999, user_id=1)
        assert result is None
